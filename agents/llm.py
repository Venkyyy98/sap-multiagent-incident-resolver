"""LLM client abstraction. Real Claude API or deterministic mock for offline dev/CI."""
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


def call_llm(prompt: str, task: str, system: str = "") -> str:
    if settings.mock_mode or not settings.openai_api_key:
        return MOCK_RESPONSES.get(task, "{}")
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.llm_model,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system or "You are an expert SAP CPI integration engineer. Respond ONLY with what is asked."},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content
