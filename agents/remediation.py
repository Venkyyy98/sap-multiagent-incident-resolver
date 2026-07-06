"""Remediation Agent: decides fix strategy with human-in-the-loop confidence gating."""
import json
from pathlib import Path
from orchestrator.state import IncidentState
from agents.llm import call_llm
from config import settings

ACTION_MAP_PATH = Path(__file__).parent.parent / "data" / "action_map.json"


def _load_action_map() -> dict:
    """Reloaded on every call so actions taught via /feedback take effect immediately, no restart needed."""
    if ACTION_MAP_PATH.exists():
        return json.loads(ACTION_MAP_PATH.read_text())
    return {}


def remediation_agent(state: IncidentState) -> IncidentState:
    diag = state["diagnosis"]
    kb_action = diag.get("kb_resolution")
    action_map = _load_action_map()

    if kb_action and kb_action in action_map:
        remediation = {"action": kb_action, "steps": action_map[kb_action],
                       "risk": "LOW" if diag["confidence"] > 0.85 else "MEDIUM"}
    else:
        raw = call_llm(f"Diagnosis: {json.dumps(diag)}\nReturn ONLY JSON: {{\"action\": str, \"steps\": [str], \"risk\": \"LOW\"|\"MEDIUM\"|\"HIGH\"}}",
                       task="remediation")
        try:
            remediation = json.loads(raw.replace("```json", "").replace("```", "").strip())
        except json.JSONDecodeError:
            remediation = {"action": "ESCALATE", "steps": ["Manual review required"], "risk": "HIGH"}

    # Human-in-the-loop gate: auto-approve only high-confidence, low-risk fixes
    auto = diag["confidence"] >= settings.confidence_threshold and remediation["risk"] == "LOW"
    log = state["log"]
    log.append(f"[Remediation] {state['enriched']['incident_id']}: {remediation['action']} | "
               f"{'auto-approved' if auto else 'ESCALATED for human approval'}")
    return {**state, "remediation": remediation, "approved": auto, "needs_human": not auto, "log": log}
