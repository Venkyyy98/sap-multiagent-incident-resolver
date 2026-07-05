"""Remediation Agent: decides fix strategy with human-in-the-loop confidence gating."""
import json
from orchestrator.state import IncidentState
from agents.llm import call_llm
from config import settings

ACTION_MAP = {
    "ROTATE_CREDENTIALS": ["Rotate client secret in CPI Security Material", "Redeploy iFlow", "Retry failed messages"],
    "ENABLE_PAGINATION": ["Enable pagination (batch 200) in request-reply", "Raise HTTP timeout to 120s", "Reprocess payload"],
    "PATCH_MAPPING": ["Add mapWithDefault for optional date fields", "Deploy mapping patch", "Reprocess message"],
    "ESCALATE_TO_BASIS": ["Create WE20 partner profile", "Reprocess SM58 tRFC entries", "Confirm with Basis team"],
    "UPDATE_KEYSTORE": ["Import new SSH host key to known_hosts", "Renew certificate", "Redeploy and test connection"],
    "ASYNC_DECOUPLE": ["Introduce JMS queue between sender/receiver", "Redeploy split iFlows"],
}


def remediation_agent(state: IncidentState) -> IncidentState:
    diag = state["diagnosis"]
    kb_action = diag.get("kb_resolution")

    if kb_action and kb_action in ACTION_MAP:
        remediation = {"action": kb_action, "steps": ACTION_MAP[kb_action],
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
