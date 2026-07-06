"""Executor Agent: carries out a narrow, explicit allowlist of safe, reversible mitigations
against the live SAP CPI tenant — redeploy/restart plus honest, evidence-based verification.

Deliberately NOT in scope (and never auto-executed, regardless of confidence):
- ROTATE_CREDENTIALS: needs a new secret from whatever external system issued it — outside
  this pipeline's trust boundary.
- PATCH_MAPPING / ESCALATE_TO_BASIS / UPDATE_KEYSTORE / ASYNC_DECOUPLE: code changes,
  cross-team handoffs, or architecture changes — require human judgment, not a redeploy.

What this agent actually does: redeploy the iFlow (clears stuck runtime state), confirm the
redeploy genuinely completed (poll until STARTED), then check for any new failures in the
minutes after — reported honestly as "no new failures observed in this window", never as a
false "confirmed fixed" claim, since re-triggering the original failure would require storing
the operator's SAP BTP login, which this system will not do.
"""
import time
from datetime import datetime, timezone
from connectors import sap_cpi

VERIFICATION_WINDOW_S = 20


def execute_mitigation(iflow_id: str, incident_id: str) -> dict:
    if not sap_cpi.deploy_capable():
        return {
            "executed": False,
            "outcome": "NOT_EXECUTABLE",
            "detail": "No deploy-capable credential configured (CPI_DEPLOY_CLIENT_ID/SECRET missing in .env). "
                      "This action can only be recommended, not carried out, until that's set up.",
        }

    since = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    trace = [f"[Executor] {incident_id}: redeploying '{iflow_id}' to clear runtime state"]

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
