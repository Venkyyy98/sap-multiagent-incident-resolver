"""Reporting Agent: generates postmortem reports and stakeholder summaries."""
import json
from pathlib import Path
from orchestrator.state import IncidentState
from agents.llm import call_llm

REPORTS_DIR = Path(__file__).parent.parent / "reports"


def reporting_agent(state: IncidentState) -> IncidentState:
    inc, diag, rem = state["enriched"], state["diagnosis"], state["remediation"]
    inc_id = inc["incident_id"]

    llm_summary = call_llm(
        f"Write a concise postmortem for:\nIncident: {json.dumps(inc)}\nDiagnosis: {json.dumps(diag)}\nRemediation: {json.dumps(rem)}",
        task="report")

    report = f"""# Postmortem: {inc_id}

| Field | Value |
|---|---|
| iFlow | {inc['iflow']} |
| Severity | {inc['severity']} |
| Business impact | {inc['business_impact']} |
| Error type | {inc['error_type']} |
| Root cause | {diag['root_cause']} |
| Confidence | {diag['confidence']:.2f} |
| Action | {rem['action']} ({rem['risk']} risk) |
| Status | {'Auto-remediated' if state['approved'] else 'Pending human approval'} |

## Remediation steps
{chr(10).join(f'{i+1}. {s}' for i, s in enumerate(rem['steps']))}

## Analysis
{llm_summary}
"""
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"{inc_id}.md"
    path.write_text(report)

    log = state["log"]
    log.append(f"[Reporting] Postmortem written → reports/{inc_id}.md")
    return {**state, "report_path": str(path), "log": log}
