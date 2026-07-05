"""LLM client abstraction. Real OpenAI API or deterministic mock for offline dev/CI."""
import json
from config import settings

MOCK_RESPONSES = {
    "diagnosis": json.dumps({
        "root_cause": "Derived from retrieved KB context (mock mode).",
        "category": "KNOWN_PATTERN",
        "confidence": 0.9,
        "evidence": ["Matched similar historical incident in knowledge base"]
    }),
    "remediation": json.dumps({
        "action": "RETRY",
        "steps": ["Apply KB-recommended fix", "Redeploy iFlow", "Retry failed messages"],
        "risk": "LOW"
    }),
    "report": "## Postmortem (mock mode)\n\nIncident resolved via knowledge-base matched remediation. Enable a real API key for full LLM-generated postmortems."
}


def _fallback(task: str, err: str) -> str:
    """Safe responses when the LLM is unreachable — always routes the incident to a human."""
    return {
        "diagnosis": json.dumps({
            "root_cause": f"Automatic diagnosis unavailable — LLM call failed ({err}). Manual review required.",
            "category": "NOVEL",
            "confidence": 0.0,
            "evidence": [],
        }),
        "remediation": json.dumps({
            "action": "ESCALATE",
            "steps": ["LLM unavailable — engineer must diagnose and remediate manually"],
            "risk": "HIGH",
        }),
        "report": f"## Postmortem unavailable\n\nThe reporting LLM call failed ({err}). "
                  f"Structured diagnosis and remediation fields above still apply; only the narrative summary is missing.",
    }.get(task, "{}")


def call_llm(prompt: str, task: str, system: str = "") -> str:
    if settings.mock_mode or not settings.openai_api_key:
        return MOCK_RESPONSES.get(task, "{}")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=1024,
            timeout=30,
            messages=[
                {"role": "system", "content": system or "You are an expert SAP CPI integration engineer. Respond ONLY with what is asked."},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content
    except Exception as e:
        return _fallback(task, type(e).__name__)
