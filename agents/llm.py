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


def call_llm_agentic(prompt: str, tools: list[dict], tool_impls: dict, system: str = "",
                     max_rounds: int = 4) -> tuple[str, list[str]]:
    """Tool-calling investigation loop: the model decides which tools to call and when it has
    enough evidence to answer. Returns (final_text, trace_of_tool_calls). Falls back to the
    single-shot mock response in offline/mock mode, since tools need a live API to be meaningful."""
    if settings.mock_mode or not settings.openai_api_key:
        return MOCK_RESPONSES.get("diagnosis", "{}"), []

    trace: list[str] = []
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        messages = [
            {"role": "system", "content": system or "You are an expert SAP CPI integration engineer investigating an incident. "
                                                     "Use the available tools to gather evidence before answering."},
            {"role": "user", "content": prompt},
        ]
        for _ in range(max_rounds):
            resp = client.chat.completions.create(
                model=settings.llm_model, max_tokens=1024, timeout=30,
                messages=messages, tools=tools, tool_choice="auto",
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                return msg.content, trace
            messages.append({"role": "assistant", "content": msg.content,
                             "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                args = json.loads(tc.function.arguments or "{}")
                impl = tool_impls.get(fn_name)
                result = impl(**args) if impl else f"Unknown tool: {fn_name}"
                trace.append(f"called {fn_name}({args}) → {result[:200]}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
        # Exceeded max_rounds without a final answer — force one more completion without tools
        resp = client.chat.completions.create(model=settings.llm_model, max_tokens=1024, timeout=30, messages=messages)
        return resp.choices[0].message.content, trace
    except Exception as e:
        return _fallback("diagnosis", type(e).__name__), trace
