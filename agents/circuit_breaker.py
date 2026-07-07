"""Circuit Breaker: autonomously stops an iFlow — no human click — once a contain-the-damage
root cause has failed repeatedly on the live tenant.

This is the "kill switch" pattern from production ops. It deliberately trips only when ALL of:
  1. auto-stop is enabled (config),
  2. the diagnosed remediation is a STOP-type root cause (cert/credential/bad-payload — the cases
     where every further message either fails identically or creates a wrong record),
  3. the incident was auto-approved (high confidence, low risk), and
  4. the flow has failed at least `auto_stop_failure_threshold` times recently — evidence of a
     sustained problem, not a single transient blip.

The threshold is what separates a real circuit breaker from a hair-trigger that causes more
outages than it prevents. Stopping is reversible: a human fixes the root cause and redeploys.
"""
from orchestrator.state import IncidentState
from connectors import sap_cpi
from config import settings


def circuit_breaker_agent(state: IncidentState) -> IncidentState:
    rem = state.get("remediation", {})
    inc = state["enriched"]
    iflow = inc.get("iflow", "")
    log = state["log"]

    def hold(reason: str) -> IncidentState:
        return {**state, "auto_action": {"triggered": False, "reason": reason}, "log": log}

    if not settings.auto_stop_enabled:
        return hold("auto-stop disabled by config")
    if rem.get("execution_type") != "STOP" or not state.get("approved"):
        return hold("not a STOP-type auto-approved incident")

    try:
        count = sap_cpi.recent_failure_count(iflow, settings.auto_stop_lookback_hours)
    except Exception as e:
        log.append(f"[CircuitBreaker] Could not read failure history for '{iflow}' ({type(e).__name__}) — not auto-stopping")
        return hold("failure history unavailable")

    if count < settings.auto_stop_failure_threshold:
        log.append(f"[CircuitBreaker] '{iflow}' has {count} recent failure(s), below threshold "
                   f"{settings.auto_stop_failure_threshold} — holding (a human can still stop it manually)")
        return hold(f"{count} failures below threshold {settings.auto_stop_failure_threshold}")

    log.append(f"[CircuitBreaker] '{iflow}' failed {count} times (>= {settings.auto_stop_failure_threshold}) "
               f"with a contain-the-damage root cause — STOPPING AUTOMATICALLY, no human needed")

    if not sap_cpi.deploy_capable():
        log.append("[CircuitBreaker] No deploy-capable credential configured — cannot actuate the stop")
        return {**state, "auto_action": {"triggered": True, "success": False, "failure_count": count,
                                         "detail": "Breaker tripped but no deploy credential to actuate the stop."}, "log": log}

    try:
        sap_cpi.stop_iflow(iflow)
        stopped = sap_cpi.poll_until_stopped(iflow, timeout_s=60, interval_s=5)
    except Exception as e:
        log.append(f"[CircuitBreaker] Auto-stop request failed: {type(e).__name__}: {e}")
        return {**state, "auto_action": {"triggered": True, "success": False, "failure_count": count,
                                         "detail": f"{type(e).__name__}: {e}"}, "log": log}

    if not stopped:
        log.append(f"[CircuitBreaker] Stop issued for '{iflow}' but not yet confirmed undeployed")
        return {**state, "auto_action": {"triggered": True, "success": False, "failure_count": count,
                                         "detail": "Undeploy accepted but not confirmed within timeout."}, "log": log}

    log.append(f"[CircuitBreaker] '{iflow}' STOPPED automatically after {count} failures — damage contained; "
               f"a human must fix the root cause and redeploy")
    return {**state, "auto_action": {"triggered": True, "success": True, "failure_count": count,
                                     "detail": f"Circuit breaker tripped: flow auto-stopped after {count} failures to "
                                               f"prevent further damage. Awaiting human fix and redeploy."}, "log": log}
