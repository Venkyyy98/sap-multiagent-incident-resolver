"""Monitor Agent: detects, validates, and enriches incoming CPI incidents."""
from orchestrator.state import IncidentState

SEVERITY_WEIGHT = {"P1": 1.0, "P2": 0.6, "P3": 0.3}


def monitor_agent(state: IncidentState) -> IncidentState:
    inc = state["incident"]
    # Priority scoring: severity + retry exhaustion + payload size signal
    score = (
        SEVERITY_WEIGHT.get(inc.get("severity", "P3"), 0.3)
        + min(inc.get("retry_count", 0) / 10, 0.3)
        + (0.2 if inc.get("payload_size_kb", 0) > 1000 else 0.0)
    )
    enriched = {
        **inc,
        "business_impact": "HIGH" if score >= 1.0 else "MEDIUM" if score >= 0.6 else "LOW",
        "keywords": _extract_keywords(inc.get("message", "")),
    }
    log = state.get("log", [])
    log.append(f"[Monitor] {inc['incident_id']} ({inc['severity']}) on '{inc['iflow']}' — priority {score:.2f}, impact {enriched['business_impact']}")
    return {**state, "enriched": enriched, "priority_score": round(score, 2), "log": log}


def _extract_keywords(message: str) -> list[str]:
    signals = ["timeout", "401", "OAuth", "mapping", "IDoc", "partner profile",
               "SFTP", "certificate", "known_hosts", "xsd:date", "tRFC"]
    return [s for s in signals if s.lower() in message.lower()]
