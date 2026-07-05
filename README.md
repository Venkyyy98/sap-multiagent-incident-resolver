# SAP IntelliOps — Multi-Agent Incident Resolver

A multi-agent AI system that **monitors, diagnoses, and recommends remediation** for SAP Cloud Integration (CPI) iFlow failures — built with **LangGraph**, **RAG (ChromaDB + OpenAI embeddings)**, and the **OpenAI API**.

It connects to a **real SAP CPI tenant**, pulls genuinely-failed messages, and runs each one through a 4-agent pipeline that produces a grounded root-cause, a confidence-scored fix recommendation, and an automatic postmortem.

> **Decision-support, not auto-execution.** This system diagnoses failures and *recommends* remediation for an engineer (or downstream automation) to carry out. It does **not** execute changes against the SAP tenant — a deliberate design choice, since actions like rotating credentials require access to systems outside the pipeline's control and should stay human-approved.

## Why this project

SAP integration landscapes generate large volumes of iFlow errors — OAuth failures, HTTP timeouts, mapping errors, IDoc issues. The expensive part of resolution is usually **triage**: a human opens Monitor, reads a raw stack trace, recalls what that error class means, and figures out the fix.

This system compresses that triage: it matches each failure against a knowledge base of resolved incidents, returns a specific numbered action plan, and uses a confidence threshold so only genuinely uncertain failures interrupt a human — while producing a consistent audit trail for every incident.

## Architecture

```
                ┌──────────────────────────────────────────┐
                │            LangGraph Orchestrator          │
                └──────────────────────────────────────────┘
 Incident ──▶ Monitor ──▶ Diagnosis ──▶ Remediation ──▶ Reporting
             (enrich,     (RAG + LLM     (action plan +    (postmortem +
              priority)    root cause)    confidence gate)   audit trail)
                              │
                              ▼
                     ChromaDB Vector Store
                  (resolved-incident knowledge base)
```

Real failures reach the pipeline through a live connector:

```
 SAP CPI Trial iFlow ──▶ MessageProcessingLogs OData API ──▶ connectors/sap_cpi.py ──▶ data/live_incidents.json ──▶ pipeline
```

### Agents

| Agent | Role |
|---|---|
| **Monitor** | Enriches the incident, extracts error keywords, computes a priority score from severity + retry exhaustion + payload size |
| **Diagnosis** | RAG over a resolved-incident knowledge base + LLM reasoning → root cause, category, confidence |
| **Remediation** | Maps the diagnosis to a concrete action plan (steps + risk), then applies a **confidence + risk gate** to auto-approve or escalate |
| **Reporting** | Generates a markdown postmortem describing the *recommended* remediation and a full agent trace |

### The human-in-the-loop gate

A remediation is fast-tracked (`auto-approved`) only when **confidence ≥ 0.85 AND risk = LOW**. Anything below that is flagged **needs human review**. In practice:

- A failure whose error text matches a known resolved pattern → high confidence → auto-approved.
- A novel failure the knowledge base has never seen → low confidence → escalated.

## Proven end-to-end against a real tenant

Three failure types were **genuinely triggered** on a live SAP CPI trial tenant, pulled via the OData connector, and resolved through the pipeline:

| iFlow | Failure triggered | Classified as | Confidence | Outcome |
|---|---|---|---|---|
| `Test-OAuth-Fail-Flow` | OAuth2 `invalid_client` (bad credentials) | `AUTH_FAILURE` | 0.88 | ✅ Auto-approved → `ROTATE_CREDENTIALS` |
| `Test-Timeout-Flow` | HTTP timeout / connection dropped | `HTTP_TIMEOUT` | 0.88 | ✅ Auto-approved → `ASYNC_DECOUPLE` |
| `Test-Fail-Flow` | Runtime exception in a Groovy script | `UNKNOWN` (no KB match) | 0.60 | ⚠ Escalated for human review |

The remaining knowledge-base categories (`MAPPING_ERROR`, `IDOC_FAILURE`, `CERT_EXPIRY`) are demonstrated via curated sample incidents rather than live triggers, since reproducing them requires standing up additional backend infrastructure.

## Key engineering concepts

- **Multi-agent orchestration** with LangGraph (state graph, conditional routing — trivial noise skips straight to reporting)
- **RAG** with a two-tier embedder: OpenAI `text-embedding-3-small` when a key is present, falling back to a deterministic offline hashed embedder for tests/CI
- **Hybrid confidence signal** — LLM self-reported confidence is grounded against retrieval similarity, so novel patterns are forced to human review
- **Human-in-the-loop gating** on confidence *and* risk
- **Graceful degradation** — LLM outages, embedding-API failures, and unreachable-tenant errors all route to a safe, human-readable state instead of crashing
- **Structured LLM outputs** validated with Pydantic
- **Live dashboard** (SAP Fiori-inspired) + FastAPI REST layer
- pytest suite

## Quickstart

```bash
git clone https://github.com/Venkyyy98/sap-multiagent-incident-resolver.git
cd sap-multiagent-incident-resolver
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add OPENAI_API_KEY (leave blank to run in offline mock mode)

# 1. Build the RAG knowledge base
python -m rag.ingest

# 2. Run the pipeline over sample incidents
python run_pipeline.py

# 3. Start the API + dashboard
uvicorn api.main:app --reload   # open http://localhost:8000
```

### Optional — connect a real SAP CPI tenant

Add your Process Integration Runtime credentials to `.env`:

```
CPI_TOKEN_URL=https://<tenant>.authentication.<region>.hana.ondemand.com/oauth/token
CPI_CLIENT_ID=...
CPI_CLIENT_SECRET=...
CPI_BASE_URL=https://<tenant>.<region>.hana.ondemand.com/api/v1
```

Then pull genuinely-failed messages into the dashboard:

```bash
python -m connectors.sap_cpi   # writes data/live_incidents.json
```

## Sample output

```
[Monitor]     AGpKfn6...clQM (P1) on 'Test-OAuth-Fail-Flow' — priority 1.00, impact HIGH
[Diagnosis]   Expired client secret causing invalid_client error (confidence 0.88)
[Remediation] ROTATE_CREDENTIALS | auto-approved
[Reporting]   Postmortem written → reports/AGpKfn6...clQM.md
```

## Tech stack

Python 3.14 · LangGraph · OpenAI API (chat + embeddings) · ChromaDB · FastAPI · Pydantic · pytest · Docker

## Project structure

```
agents/         # 4 specialized agents (monitor, diagnosis, remediation, reporting)
orchestrator/   # LangGraph state graph wiring
rag/            # ingestion + retrieval (ChromaDB, pluggable embedders)
connectors/     # live SAP CPI OData connector
api/            # FastAPI service + Fiori-inspired dashboard
data/           # sample incidents, live incidents, knowledge base
tests/          # pytest suite
```

## Roadmap

- [ ] Optional executor agent — carry out low-risk, reversible actions (message resubmission, iFlow redeploy) behind an explicit action allowlist
- [ ] Agent evaluation harness (LLM-as-judge)
- [ ] Slack/Teams notification integration
- [ ] Expand the resolved-incident knowledge base from real historical tickets

## Author

**Venkatesh Mudaliar** — SAP BTP/CPI Consultant · AI/ML Engineer
[LinkedIn](https://linkedin.com/in/venkateshcmudaliar) · [GitHub](https://github.com/Venkyyy98)
