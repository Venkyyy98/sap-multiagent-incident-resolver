"""Executor Agent: carries out a narrow, explicit allowlist of safe, reversible mitigations
against the live SAP CPI tenant, routed by the *type* of failure — not one blunt action for
everything.

Two execution types are actually carried out:
- STOP: undeploy the iFlow so it processes no further messages. This is the correct response when
  leaving it running actively causes harm — a sender pushing bad payloads that create wrong records
  (stop before it does so 1,000 more times), or an expired certificate/credential that will only
  keep failing. Redeploying those would just fail again identically; stopping halts the damage and
  hands a clean, held state to a human to fix the root cause and redeploy.
- REDEPLOY: restart the iFlow to clear transient stuck runtime state (e.g. a one-off connectivity
  blip). An immediate mitigation, not a structural fix — the structural fix (pagination, decoupling)
  is still surfaced as a recommendation.

Everything else is execution_type NONE: recommended for a human, never auto-executed — credential
rotation (needs a secret from outside this system), mapping/script code changes, cross-team handoffs.
Which action maps to which type is defined in data/action_map.json, and the /execute gate re-derives
it server-side rather than trusting the caller.
"""
import time
from datetime import datetime, timezone
from connectors import sap_cpi

VERIFICATION_WINDOW_S = 20


def execute_mitigation(iflow_id: str, incident_id: str, execution_type: str) -> dict:
    if not sap_cpi.deploy_capable():
        return {
            "executed": False,
            "outcome": "NOT_EXECUTABLE",
            "detail": "No deploy-capable credential configured (CPI_DEPLOY_CLIENT_ID/SECRET missing in .env). "
                      "This action can only be recommended, not carried out, until that's set up.",
        }

    if execution_type == "STOP":
        return _execute_stop(iflow_id, incident_id)
    if execution_type == "REDEPLOY":
        return _execute_redeploy(iflow_id, incident_id)
    return {
        "executed": False,
        "outcome": "RECOMMEND_ONLY",
        "detail": "This remediation is not on the auto-executable allowlist (it needs human judgment or "
                  "access outside this pipeline). The recommended steps stand as guidance for a human.",
    }


def _execute_stop(iflow_id: str, incident_id: str) -> dict:
    trace = [f"[Executor] {incident_id}: STOPPING '{iflow_id}' — leaving it running would keep failing/"
             f"mis-processing messages"]
    try:
        sap_cpi.stop_iflow(iflow_id)
    except Exception as e:
        trace.append(f"[Executor] Stop request failed: {type(e).__name__}: {e}")
        return {"executed": False, "outcome": "STOP_FAILED", "detail": str(e), "trace": trace}

    if not sap_cpi.poll_until_stopped(iflow_id, timeout_s=60, interval_s=5):
        trace.append("[Executor] Stop issued but the flow still shows deployed within the timeout window")
        return {"executed": True, "outcome": "STOP_INCOMPLETE",
                "detail": "Undeploy was accepted but not yet confirmed. Verify manually in Monitor.", "trace": trace}

    trace.append(f"[Executor] '{iflow_id}' is STOPPED — it will process no further messages until a human "
                 f"fixes the root cause and redeploys")
    return {
        "executed": True, "outcome": "STOPPED",
        "detail": "Flow halted to contain the blast radius — no further messages will be mis-processed or "
                  "fail against the same broken condition. This is a holding action: a human still needs to "
                  "apply the underlying fix (rotate the credential / correct the mapping / renew the cert) "
                  "and redeploy.",
        "trace": trace,
    }


def _execute_redeploy(iflow_id: str, incident_id: str) -> dict:
    since = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    trace = [f"[Executor] {incident_id}: redeploying '{iflow_id}' to clear transient runtime state"]

    try:
        sap_cpi.redeploy_iflow(iflow_id)
    except Exception as e:
        trace.append(f"[Executor] Redeploy request failed: {type(e).__name__}: {e}")
        return {"executed": False, "outcome": "REDEPLOY_FAILED", "detail": str(e), "trace": trace}

    status = sap_cpi.poll_until_started(iflow_id, timeout_s=180, interval_s=10)
    if status.get("Status") != "STARTED":
        trace.append(f"[Executor] Redeploy did not reach STARTED within timeout (last status: {status.get('Status')})")
        return {"executed": True, "outcome": "REDEPLOY_INCOMPLETE", "detail": f"Last status: {status.get('Status')}",
                "trace": trace}

    trace.append(f"[Executor] Redeploy confirmed — '{iflow_id}' is STARTED (DeployedOn {status.get('DeployedOn')})")

    trace.append(f"[Executor] Watching for new failures for {VERIFICATION_WINDOW_S}s "
                 f"(cannot re-trigger the original failure without the operator's SAP login, by design)")
    time.sleep(VERIFICATION_WINDOW_S)
    try:
        new_failures = sap_cpi.failures_since(iflow_id, since)
    except Exception as e:
        trace.append(f"[Executor] Post-redeploy failure check errored: {type(e).__name__}: {e}")
        new_failures = None

    if new_failures is None:
        outcome, detail = "MITIGATED_UNVERIFIED", "Redeployed successfully; could not confirm absence of new failures."
    elif new_failures:
        outcome = "ISSUE_PERSISTS"
        detail = f"Redeployed, but {len(new_failures)} new failure(s) logged since — mitigation did not resolve it. Escalating."
    else:
        outcome = "MITIGATED_NO_NEW_FAILURES"
        detail = ("Redeployed successfully; no new failures observed in the verification window. "
                  "Note: this iFlow has no organic production traffic, so absence of failures here is a weak "
                  "signal, not confirmation the original trigger condition is resolved.")

    trace.append(f"[Executor] Outcome: {outcome} — {detail}")
    return {"executed": True, "outcome": outcome, "detail": detail, "trace": trace}
