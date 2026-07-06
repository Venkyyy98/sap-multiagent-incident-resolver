"""Diagnosis Agent: agentic, tool-using root cause analysis grounded in RAG + live tenant evidence."""
import json
from orchestrator.state import IncidentState
from agents.llm import call_llm_agentic
from agents.tools import TOOL_SCHEMAS, TOOL_IMPLS
from rag.retrieve import retrieve_similar


def diagnosis_agent(state: IncidentState) -> IncidentState:
    inc = state["enriched"]
    query = f"{inc['error_type']}: {inc['message']}"

    # Initial retrieval seeds the prompt so the model has *something* even if it never calls a tool.
    try:
        hits = retrieve_similar(query, k=3)
    except Exception as e:
        hits = []  # retrieval down (e.g. embedding API unreachable) → proceed with no KB grounding
        state["log"].append(f"[Diagnosis] KB retrieval unavailable ({type(e).__name__}) — continuing without historical context")
    context = "\n".join(f"- ({h['similarity']}) {h['text']}" for h in hits)

    prompt = f"""Incident: {json.dumps(inc, indent=2)}

Similar historical incidents (initial search):
{context}

You have tools available: search_knowledge_base (try refined queries if this initial search is weak),
get_iflow_deployment_info (check for a recent deploy that might explain a regression), and
count_recent_failures (check whether this is a one-off or a recurring pattern). Use whichever help you
reach a confident, well-evidenced conclusion — you don't have to call all of them.

When you're done investigating, respond with ONLY this JSON (no tool call):
{{"root_cause": str, "category": "KNOWN_PATTERN"|"NOVEL", "confidence": 0-1, "evidence": [str]}}"""

    raw, tool_trace = call_llm_agentic(prompt, tools=TOOL_SCHEMAS, tool_impls=TOOL_IMPLS)
    for line in tool_trace:
        state["log"].append(f"[Diagnosis] {line}")

    try:
        diagnosis = json.loads(raw.replace("```json", "").replace("```", "").strip())
    except json.JSONDecodeError:
        diagnosis = {"root_cause": raw[:300], "category": "NOVEL", "confidence": 0.4, "evidence": []}

    # Ground confidence with retrieval similarity (hybrid signal).
    # "UNKNOWN" is a sentinel meaning "no known category matched" — it is not itself a reusable
    # taxonomy bucket. Excluding it here matters: without this, teaching ONE fix for one novel
    # "UNKNOWN" incident would silently become a wildcard that boosts confidence for every future
    # unrelated novel error, since they'd all share the same "UNKNOWN" label. Only a genuine
    # near-duplicate text match (below) should earn trust for incidents in this bucket.
    match = next((h for h in hits if h["error_type"] == inc["error_type"] and inc["error_type"] != "UNKNOWN"), None)
    best = hits[0] if hits else None
    if match and match["similarity"] > 0.2:
        diagnosis["confidence"] = max(diagnosis.get("confidence", 0.5), 0.88)
        diagnosis["kb_resolution"] = match["resolution"]
    elif best and best["similarity"] > 0.9:
        # Near-duplicate text match even without a matching taxonomy label — e.g. a freshly-taught
        # precedent whose error_type classification doesn't line up perfectly. Trust it anyway: this
        # is what lets the KB "learn" from human-confirmed resolutions via /feedback.
        diagnosis["confidence"] = max(diagnosis.get("confidence", 0.5), 0.85)
        diagnosis["kb_resolution"] = best["resolution"]
    elif not match:
        diagnosis["confidence"] = min(diagnosis.get("confidence", 0.5), 0.6)  # novel pattern → force human review

    log = state["log"]
    log.append(f"[Diagnosis] {inc['incident_id']}: {diagnosis['root_cause'][:80]}... (confidence {diagnosis['confidence']:.2f})")
    return {**state, "retrieved_context": [h["text"] for h in hits], "diagnosis": diagnosis, "log": log}
