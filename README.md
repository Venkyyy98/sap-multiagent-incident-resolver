# SAP IntelliOps — Multi-Agent Incident Resolver

An **agentic AI system** for autonomous triage and remediation planning of SAP Cloud Integration (CPI) iFlow failures. It orchestrates four task-specialized LLM agents as a **LangGraph directed state graph**, grounds every diagnosis in a **retrieval-augmented generation (RAG)** layer backed by a vector store of resolved incidents, and integrates directly with a **live SAP CPI tenant** over the OData v2 Message Processing Logs API.

Each genuinely-failed message is ingested from the tenant, enriched, semantically matched against historical precedent, diagnosed with a hybrid confidence signal, and routed through a **confidence-and-risk-gated human-in-the-loop policy** that either fast-tracks the remediation or escalates it — emitting a structured postmortem and full agent execution trace for every incident.

> **Design stance — decision-support, not blind auto-execution.** The system produces high-confidence, grounded remediation *recommendations* for an engineer or a downstream executor to action. It deliberately does **not** mutate the SAP tenant, because the highest-value remediations (credential rotation, mapping patches) depend on systems outside the pipeline's trust boundary and must remain human-governed. Autonomy is gated by an explicit confidence-and-risk policy rather than assumed.

---

## System architecture

```
                      ┌─────────────────────────────────────────────────────┐
                      │      LangGraph Orchestrator (typed state graph)      │
                      │      conditional routing · deterministic handoffs    │
                      └─────────────────────────────────────────────────────┘

  CPI OData API ─▶ [Monitor] ─▶ [Diagnosis] ─▶ [Remediation] ─▶ [Reporting] ─▶ Postmortem + Trace
   (ingestion)     enrich +      RAG-grounded    policy-gated      LLM-authored
                   priority       root cause      action plan       audit record
   score           analysis      confidence + risk
                                       ▲
                                       │  dense vector retrieval (cosine / HNSW)
                                       ▼
                          ┌──────────────────────────────┐
                          │  ChromaDB Vector Store         │
                          │  resolved-incident corpus      │
                          │  OpenAI text-embedding-3-small │
                          └──────────────────────────────┘
```

### Live tenant integration path

```
SAP CPI Trial iFlow ──(fails)──▶ MessageProcessingLogs (OData v2)
        │                                   │
        │  OAuth2 client-credentials grant  │  media-link entity resolution
        │                                   ▼   (ErrorInformation/$value)
        └──────────▶ connectors/sap_cpi.py ──▶ error-taxonomy classification
                                             ──▶ data/live_incidents.json ──▶ pipeline
```

---

## Agent topology

The pipeline is a compiled `StateGraph` over a typed shared state (`IncidentState`, a `TypedDict`). The entry node fans out through a **conditional edge**: trivial, low-priority noise short-circuits directly to reporting, while actionable incidents traverse the full diagnostic chain.

| Agent | Responsibility | Techniques |
|---|---|---|
| **Monitor** | Ingests and validates the incident, extracts error signal keywords, computes a composite **priority score** (severity weight + retry-exhaustion signal + payload-size heuristic) and derives business impact. | Deterministic feature scoring, structured enrichment |
| **Diagnosis** | Executes **dense vector retrieval** against the resolved-incident corpus, injects the top-k precedents as grounding context, and prompts the LLM for a JSON-constrained root-cause hypothesis. Reconciles the model's self-reported confidence with retrieval similarity into a **hybrid confidence signal**. | RAG, semantic embeddings, retrieval grounding, structured generation |
| **Remediation** | Maps the diagnosis to a concrete, ordered action plan (steps + risk classification), then applies a **confidence-and-risk gate** to decide auto-approval vs. escalation. | Policy-based autonomy gating, human-in-the-loop guardrails |
| **Reporting** | Synthesizes a stakeholder-ready markdown postmortem and persists the full agent execution trace as an auditable record. | LLM summarization, structured artifact generation |

---

## Engineering deep-dive

### Retrieval-augmented diagnosis with hybrid confidence grounding
Diagnosis is not a naked LLM call. The incident is embedded and matched against a curated corpus of resolved incidents in **ChromaDB** (cosine similarity over an HNSW index). The retrieved precedents are injected into the prompt as grounding context, and — critically — the LLM's self-reported confidence is **reconciled against retrieval similarity**: when a strong precedent exists in the same error category, confidence is anchored high; when the failure is genuinely novel (no category match), confidence is *forced down* to guarantee human review. This defends against overconfident hallucination on unseen failure modes.

### Pluggable embedding strategy (two-tier)
The RAG layer abstracts the embedding function behind a strategy interface:
- **Production:** OpenAI `text-embedding-3-small` (1536-dim dense semantic embeddings) — matches on *meaning*, so a `"Remotely closed"` connection drop correctly aligns with a `"recurring timeout"` precedent despite zero shared vocabulary.
- **Offline / CI:** a deterministic hashed bag-of-words embedder — zero external dependencies, fully reproducible, keeps the test suite hermetic.

The active embedder is selected at runtime from configuration, so the pipeline degrades to a fully offline mode with no code change.

### Live SAP CPI ingestion
`connectors/sap_cpi.py` authenticates to the tenant via an **OAuth2 client-credentials grant**, queries `MessageProcessingLogs` filtered on `Status eq 'FAILED'`, and resolves each failure's exception payload from its **media-link entity** (`ErrorInformation/$value`) — a detail the default OData projection omits. Raw error text is then normalized into a stable **error taxonomy** (`AUTH_FAILURE`, `HTTP_TIMEOUT`, `MAPPING_ERROR`, …) that aligns tenant reality with the knowledge-base schema. Genuine failures are provoked end-to-end against the tenant's HTTPS sender via an authenticated **CSRF-token handshake**.

### Policy-gated autonomy (human-in-the-loop)
A remediation is fast-tracked only when it satisfies a compound predicate — **confidence ≥ threshold AND risk = LOW**. Everything else is escalated. This makes the autonomy boundary an explicit, auditable policy rather than an emergent property of the model.

### Graceful degradation across every external boundary
LLM provider outages, embedding-API failures, and unreachable-tenant conditions are all caught and mapped to a **safe, human-readable escalation state** — the pipeline never surfaces a raw traceback or crashes mid-incident. Failure is a routed state, not an exception.

---

## Validated end-to-end against a live tenant

Three failure classes were **genuinely provoked** on a live SAP CPI trial tenant, ingested via the OData connector, and resolved through the full agent graph:

| iFlow | Provoked failure | Taxonomy | Hybrid confidence | Policy outcome |
|---|---|---|---|---|
| `Test-OAuth-Fail-Flow` | OAuth2 `invalid_client` (bad credentials) | `AUTH_FAILURE` | **0.88** | ✅ Auto-approved → `ROTATE_CREDENTIALS` |
| `Test-Timeout-Flow` | HTTP timeout / connection reset | `HTTP_TIMEOUT` | **0.88** | ✅ Auto-approved → `ASYNC_DECOUPLE` |
| `Test-Fail-Flow` | Groovy runtime exception | `UNKNOWN` (no precedent) | **0.60** | ⚠ Escalated to human review |

The `Test-Fail-Flow` outcome is the system working *correctly*: a genuinely novel failure with no knowledge-base precedent is deliberately held below the autonomy threshold. The remaining taxonomy classes (`MAPPING_ERROR`, `IDOC_FAILURE`, `CERT_EXPIRY`) are exercised via curated sample incidents, as reproducing them live requires additional backend infrastructure.

---

## Technology stack

| Layer | Technology |
|---|---|
| **Agent orchestration** | LangGraph (compiled `StateGraph`, conditional edges, typed shared state) |
| **LLM reasoning** | OpenAI Chat Completions — task-specialized, JSON-constrained generation |
| **Retrieval / RAG** | ChromaDB (cosine / HNSW) · OpenAI `text-embedding-3-small` · offline hashed fallback |
| **SAP integration** | OData v2 · OAuth2 client-credentials · CSRF handshake · media-link entity resolution |
| **Service layer** | FastAPI · Pydantic-validated I/O · SAP Fiori-inspired dashboard |
| **Quality** | pytest · deterministic offline mock mode · Docker |

---

## Quickstart

```bash
git clone https://github.com/Venkyyy98/sap-multiagent-incident-resolver.git
cd sap-multiagent-incident-resolver
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add OPENAI_API_KEY (blank → deterministic offline mock mode)

python -m rag.ingest          # 1. build the RAG vector store
python run_pipeline.py        # 2. run the agent graph over sample incidents
uvicorn api.main:app --reload # 3. launch API + dashboard → http://localhost:8000
```

### Connect a live SAP CPI tenant

Provide Process Integration Runtime credentials in `.env`:

```
CPI_TOKEN_URL=https://<tenant>.authentication.<region>.hana.ondemand.com/oauth/token
CPI_CLIENT_ID=...
CPI_CLIENT_SECRET=...
CPI_BASE_URL=https://<tenant>.<region>.hana.ondemand.com/api/v1
```

```bash
python -m connectors.sap_cpi   # ingest genuinely-failed messages → data/live_incidents.json
```

---

## Project structure

```
agents/         # task-specialized agents: monitor · diagnosis · remediation · reporting
orchestrator/   # LangGraph state graph + typed shared state
rag/            # ingestion, retrieval, pluggable embedding strategies (ChromaDB)
connectors/     # live SAP CPI OData ingestion + error-taxonomy classification
api/            # FastAPI service + Fiori-inspired dashboard
data/           # sample incidents · live incidents · resolved-incident knowledge base
tests/          # pytest suite (hermetic, offline)
```

## Roadmap

- [ ] **Executor agent** — carry out low-risk, reversible actions (message resubmission, iFlow redeploy) behind an explicit action allowlist, extending policy-gated autonomy from *recommendation* to *action*
- [ ] Agent evaluation harness (LLM-as-judge) for diagnosis/remediation quality
- [ ] Slack / MS Teams escalation integration
- [ ] Knowledge-base expansion from real historical incident tickets

## Author

**Venkatesh Mudaliar** — SAP BTP/CPI Consultant · AI/ML Engineer
[LinkedIn](https://linkedin.com/in/venkateshcmudaliar) · [GitHub](https://github.com/Venkyyy98)
