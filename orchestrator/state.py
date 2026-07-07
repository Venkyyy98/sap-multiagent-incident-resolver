"""Shared state passed between agents in the LangGraph pipeline."""
from typing import TypedDict, Optional


class IncidentState(TypedDict, total=False):
    # Raw incident
    incident: dict
    # Monitor agent output
    enriched: dict
    priority_score: float
    # Diagnosis agent output
    retrieved_context: list[str]
    diagnosis: dict            # {root_cause, category, confidence, evidence}
    # Remediation agent output
    remediation: dict          # {action, steps, risk}
    approved: bool
    needs_human: bool
    # Circuit-breaker agent output (autonomous stop)
    auto_action: dict          # {triggered, success?, failure_count?, detail}
    # Reporting agent output
    report_path: Optional[str]
    log: list[str]
