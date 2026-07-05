"""Diagnosis Agent: RAG-grounded root cause analysis with structured LLM output."""
import json
from orchestrator.state import IncidentState
from agents.llm import call_llm
from rag.retrieve import retrieve_similar


def diagnosis_agent(state: IncidentState) -> IncidentState:
    inc = state["enriched"]
    query = f"{inc['error_type']}: {inc['message']}"
    hits = retrieve_similar(query, k=3)
    context = "\n".join(f"- ({h['similarity']}) {h['text']}" for h in hits)

    prompt = f"""Incident: {json.dumps(inc, indent=2)}

Similar historical incidents:
{context}

Return ONLY JSON: {{"root_cause": str, "category": "KNOWN_PATTERN"|"NOVEL", "confidence": 0-1, "evidence": [str]}}"""

    raw = call_llm(prompt, task="diagnosis")
    try:
        diagnosis = json.loads(raw.replace("```json", "").replace("```", "").strip())
    except json.JSONDecodeError:
        diagnosis = {"root_cause": raw[:300], "category": "NOVEL", "confidence": 0.4, "evidence": []}

    # Ground confidence with retrieval similarity (hybrid signal)
    match = next((h for h in hits if h["error_type"] == inc["error_type"]), None)
    if match and match["similarity"] > 0.2:
        diagnosis["confidence"] = max(diagnosis.get("confidence", 0.5), 0.88)
        diagnosis["kb_resolution"] = match["resolution"]
    elif not match:
        diagnosis["confidence"] = min(diagnosis.get("confidence", 0.5), 0.6)  # novel pattern → force human review

    log = state["log"]
    log.append(f"[Diagnosis] {inc['incident_id']}: {diagnosis['root_cause'][:80]}... (confidence {diagnosis['confidence']:.2f})")
    return {**state, "retrieved_context": [h["text"] for h in hits], "diagnosis": diagnosis, "log": log}
