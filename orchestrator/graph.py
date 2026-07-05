"""LangGraph state graph wiring the 4 agents with conditional routing."""
from langgraph.graph import StateGraph, END
from orchestrator.state import IncidentState
from agents.monitor import monitor_agent
from agents.diagnosis import diagnosis_agent
from agents.remediation import remediation_agent
from agents.reporting import reporting_agent


def route_after_monitor(state: IncidentState) -> str:
    """Skip full pipeline for trivial noise (priority < 0.3)."""
    return "diagnosis" if state["priority_score"] >= 0.3 else "reporting"


def build_graph():
    g = StateGraph(IncidentState)
    g.add_node("monitor", monitor_agent)
    g.add_node("diagnosis", diagnosis_agent)
    g.add_node("remediation", remediation_agent)
    g.add_node("reporting", reporting_agent)

    g.set_entry_point("monitor")
    g.add_conditional_edges("monitor", route_after_monitor,
                            {"diagnosis": "diagnosis", "reporting": "reporting"})
    g.add_edge("diagnosis", "remediation")
    g.add_edge("remediation", "reporting")
    g.add_edge("reporting", END)
    return g.compile()


pipeline = build_graph()
