"""Tools the Diagnosis agent can call during its investigation loop.

Each tool returns a plain string (tool-call results are always serialized back to the
model as text). CPI-backed tools degrade gracefully — if no live tenant is configured,
they say so rather than raising, so the agentic loop still completes.
"""
import json
from rag.retrieve import retrieve_similar
from connectors import sap_cpi

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Semantic search over resolved historical CPI incidents. You may call this "
                            "more than once with different phrasings if the first search doesn't surface "
                            "a clear precedent.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search text — error type and message, or a refined variant"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_iflow_deployment_info",
            "description": "Reads the live SAP CPI tenant for an iFlow's current runtime status and when it "
                            "was last deployed. Useful for judging whether a failure might be a regression "
                            "from a recent deploy versus a long-stable flow hitting an external issue.",
            "parameters": {
                "type": "object",
                "properties": {"iflow_id": {"type": "string"}},
                "required": ["iflow_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_recent_failures",
            "description": "Counts how many times this specific iFlow has failed in the tenant recently. "
                            "A high count suggests a recurring/systemic issue; a count of 1 suggests an "
                            "isolated blip.",
            "parameters": {
                "type": "object",
                "properties": {
                    "iflow_id": {"type": "string"},
                    "hours": {"type": "integer", "description": "Lookback window in hours", "default": 24},
                },
                "required": ["iflow_id"],
            },
        },
    },
]


def search_knowledge_base(query: str) -> str:
    hits = retrieve_similar(query, k=3)
    if not hits:
        return "No matches found in the knowledge base."
    return json.dumps([{"similarity": h["similarity"], "error_type": h["error_type"],
                        "resolution": h["resolution"], "text": h["text"]} for h in hits])


def get_iflow_deployment_info(iflow_id: str) -> str:
    if not (sap_cpi.BASE_URL or sap_cpi.DEPLOY_BASE_URL):
        return "No live SAP CPI tenant configured — deployment info unavailable."
    try:
        status = sap_cpi.get_runtime_status(iflow_id)
        return json.dumps({"status": status.get("Status"), "version": status.get("Version"),
                           "deployed_on": status.get("DeployedOn")})
    except Exception as e:
        return f"Could not read deployment info: {type(e).__name__}: {e}"


def count_recent_failures(iflow_id: str, hours: int = 24) -> str:
    if not (sap_cpi.BASE_URL or sap_cpi.DEPLOY_BASE_URL):
        return "No live SAP CPI tenant configured — failure history unavailable."
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        failures = sap_cpi.failures_since(iflow_id, since)
        return f"{len(failures)} failure(s) for '{iflow_id}' in the last {hours}h."
    except Exception as e:
        return f"Could not read failure history: {type(e).__name__}: {e}"


TOOL_IMPLS = {
    "search_knowledge_base": search_knowledge_base,
    "get_iflow_deployment_info": get_iflow_deployment_info,
    "count_recent_failures": count_recent_failures,
}
