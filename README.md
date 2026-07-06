# SAP IntelliOps — Multi-Agent Incident Resolver

An **agentic AI system** for closed-loop triage, diagnosis, and narrowly-scoped remediation of SAP Cloud Integration (CPI) iFlow failures. Five task-specialized agents are orchestrated as a **LangGraph directed state graph**; diagnosis is a genuine **tool-calling investigation loop** (not a fixed prompt) grounded in a **retrieval-augmented generation (RAG)** corpus of resolved incidents; and the system integrates directly with a **live SAP CPI tenant** — ingesting real failures, executing a bounded, verifiable mitigation, and **learning from human-confirmed fixes** to improve its own future confidence.

Every genuinely-failed message is ingested from the tenant, enriched, investigated by an agent that decides for itself what evidence to pull, diagnosed with a hybrid confidence signal, routed through a **confidence-and-risk-gated autonomy policy**, and — if eligible — mitigated against the real tenant with evidence-based verification. A human-confirmed resolution for anything escalated is written back into the knowledge base, so the same failure class is recognized automatically next time. Scored end-to-end against a 20-case labeled evaluation set.

> **Design stance — bounded autonomy, not blind auto-execution.** The system can genuinely *act* — but only within a narrow, explicit allowlist of safe, reversible operations (redeploy + evidence-based verification). Higher-stakes remediations (rotating a credential, patching a mapping, an architecture change) are always surfaced as *recommendations* for a human, never auto-executed — regardless of confidence — because they depend on systems or judgment outside this pipeline's trust boundary. Autonomy is earned per-action-type by explicit policy, not assumed from a confidence score.

---

## System architecture

```
                      ┌───────────────────────────────────────────────────────────────┐
                      │            LangGraph Orchestrator (typed state graph)          │
                      │            conditional routing · deterministic handoffs        │
                      └───────────────────────────────────────────────────────────────┘

  CPI OData API ─▶ [Monitor] ─▶ [Diagnosis] ─▶ [Remediation] ─▶ [Executor] ─▶ [Reporting]
   (ingestion)     enrich +     agentic tool-    policy-gated    bounded,      LLM-authored
                   priority     calling          action plan     verified      postmortem +
                   score        investigation     + risk         mitigation    audit trail
                        │             ▲                              │
                        │             │  dense vector retrieval       │  redeploy · poll ·
                        │             ▼  (cosine / HNSW)               ▼  check for new failures
                        │    ┌──────────────────────────────┐   Live SAP CPI tenant
                        │    │  ChromaDB Vector Store         │   (deploy-scoped credential)
                        │    │  resolved-incident corpus      │
                        │    │  OpenAI text-embedding-3-small │
                        │    └──────────────────────────────┘
                        │             ▲
                        └─────────────┘  human-confirmed fixes written back (learning loop)
```

### Live tenant integration path

```
SAP CPI Trial iFlow ──(fails)──▶ MessageProcessingLogs (OData v2)
        │                                   │
        │  OAuth2 client-credentials grant  │  media-link entity resolution
        │  (read-scoped credential)         ▼   (ErrorInformation/$value)
        └──────────▶ connectors/sap_cpi.py ──▶ error-taxonomy classification
                                             ──▶ data/live_incidents.json ──▶ pipeline
                                                                                  │
                          deploy-scoped credential (separate, narrower-scoped)   ▼
                          WorkspaceArtifactsDeploy / NodeManager.deploycontent ── Executor
                                             ──▶ redeploy ──▶ poll runtime status ──▶ verify
```

Two separate service keys are used deliberately: a read-only key for ingestion/monitoring, and a second, narrowly-scoped deploy-capable key (added specifically for the executor) — least privilege per capability, not one over-privileged credential.

---

## Agent topology

The pipeline is a compiled `StateGraph` over a typed shared state (`IncidentState`). The entry node fans out through a **conditional edge**: trivial, low-priority noise short-circuits directly to reporting, while actionable incidents traverse the full chain.

| Agent | Responsibility | Techniques |
|---|---|---|
| **Monitor** | Enriches the incident, extracts error signal keywords, computes a composite **priority score** and business impact. | Deterministic feature scoring |
| **Diagnosis** | Runs an **agentic, tool-calling investigation loop** — the model decides which tools to call (semantic KB search, live deployment status, recent-failure count) and when it has enough evidence, rather than following one fixed retrieval step. Reconciles self-reported confidence with retrieval similarity into a **hybrid confidence signal**. | RAG, semantic embeddings, OpenAI function-calling, retrieval grounding |
| **Remediation** | Maps the diagnosis to a concrete, ordered action plan, then applies a **confidence-and-risk gate** to decide auto-approval vs. escalation. Action definitions are loaded from a data file, so newly-taught actions apply without a code change. | Policy-based autonomy gating |
| **Executor** | For auto-approved, LOW-risk incidents: redeploys the iFlow against the live tenant, polls until the deployment genuinely completes, and checks for new failures — reporting outcomes honestly (including when the mitigation didn't hold). Gated server-side, independent of client input. | Live infrastructure actuation, evidence-based verification |
| **Reporting** | Synthesizes a stakeholder-ready markdown postmortem — explicitly framed as *recommended*, not performed, for anything the executor didn't itself carry out. | LLM summarization, structured artifact generation |

---

## Engineering deep-dive

### Agentic diagnosis: a real tool-calling investigation loop
Diagnosis is not a single fixed prompt. The model is given three tools — `search_knowledge_base` (can be called more than once with refined queries), `get_iflow_deployment_info`, and `count_recent_failures` — and runs a bounded OpenAI function-calling loop (`agents/llm.py::call_llm_agentic`), deciding for itself what evidence it needs before concluding. In practice, different incidents produce genuinely different tool-call sequences: a timeout incident checks recent failure count and concludes "isolated occurrence" rather than assuming a systemic pattern, purely from live tenant data it chose to pull.

### Hybrid confidence grounding — and the wildcard bug it can create if done naively
The LLM's self-reported confidence is reconciled against retrieval similarity: a strong precedent in the same error category anchors confidence high; a genuinely novel failure forces it down. One subtlety worth documenting honestly: `"UNKNOWN"` is a *sentinel* meaning "no known category matched," not a real taxonomy bucket. An earlier version of this logic let an exact-label match fire for `"UNKNOWN"` incidents — which meant teaching one fix for one novel error silently became a wildcard that boosted confidence for *every future unrelated* novel error, since they all share that label. Caught by the evaluation harness (escalation recall dropped to 0.00 on novel-error test cases) and fixed by excluding `"UNKNOWN"` from the exact-match path entirely — only a genuine near-duplicate text match (>0.9 similarity) can earn trust in that bucket.

### The learning loop
`POST /feedback` lets a human confirm the real root cause and fix for an escalated incident. That confirmation is written into `data/knowledge_base.json`, `data/action_map.json`, and upserted directly into the live ChromaDB collection — immediately, no re-ingest step required. Proven end-to-end: a Groovy script failure escalated at 60% confidence; after teaching the fix, the *same* incident re-diagnosed at 91.6% confidence and auto-approved.

### Bounded, verified execution
The executor is intentionally narrow: it can redeploy an iFlow and check whether new failures appear afterward, and nothing else. It cannot re-trigger the original failure to *prove* the fix worked, because that would require storing the operator's SAP BTP login — a line this system won't cross. Verification is reported honestly, including the case where a redeploy completes but the underlying issue evidently persists (`ISSUE_PERSISTS`), rather than always declaring success.

### Pluggable embedding strategy (two-tier)
OpenAI `text-embedding-3-small` (1536-dim) in production — matches on meaning, so `"Remotely closed"` correctly aligns with a `"recurring timeout"` precedent despite zero shared vocabulary — falling back to a deterministic offline hashed bag-of-words embedder for hermetic tests/CI.

### Live SAP CPI integration
`connectors/sap_cpi.py` authenticates via **OAuth2 client-credentials grants**, resolves failure payloads from their **media-link entity** (`ErrorInformation/$value`), and normalizes raw error text into a stable taxonomy. Genuine failures are provoked end-to-end via an authenticated **CSRF-token handshake** against the tenant's HTTPS sender. Deploy operations use a second, separately-scoped credential obtained by probing exactly which OAuth scopes a given service key grants (decoding the JWT rather than assuming).

### Graceful degradation across every external boundary
LLM failures, embedding-API outages, and unreachable-tenant conditions are all caught and mapped to a safe, human-readable escalation state — proven by deliberately breaking the API key mid-pipeline and confirming the incident still resolves to `ESCALATE` with a clear trace, never a crash.

---

## Evaluated against a labeled golden set

`evals/run.py` scores the pipeline over 20 labeled incidents (`evals/golden_incidents.json`) spanning all five known taxonomy categories plus four deliberately novel/unseen error patterns:

| Metric | Score |
|---|---|
| Taxonomy classification accuracy | 100% (20/20) |
| Remediation action accuracy (known-pattern cases) | 100% (16/16) |
| Escalation-gate precision / recall / F1 | 1.00 / 1.00 / 1.00 |

The first eval run scored escalation recall at **0.00** — it's what surfaced the `UNKNOWN`-wildcard bug described above. Re-running after the fix produced the scores above. Full per-incident results in `evals/results.md`.

---

## Validated end-to-end against a live tenant

Three failure classes were **genuinely provoked** on a live SAP CPI trial tenant and resolved through the full agent graph:

| iFlow | Provoked failure | Taxonomy | Confidence | Policy outcome |
|---|---|---|---|---|
| `Test-OAuth-Fail-Flow` | OAuth2 `invalid_client` (bad credentials) | `AUTH_FAILURE` | 0.90–0.95 | ✅ Auto-approved → `ROTATE_CREDENTIALS` |
| `Test-Timeout-Flow` | HTTP timeout / connection reset | `HTTP_TIMEOUT` | 0.88–0.90 | ✅ Auto-approved → `ASYNC_DECOUPLE`, then genuinely **executed** (redeploy confirmed, verification window clean) |
| `Test-Fail-Flow` | Groovy runtime exception | `UNKNOWN` → taught via `/feedback` | 0.60 → 0.916 after teaching | ⚠ Escalated → ✅ auto-approved on re-run, same incident |

The remaining taxonomy classes (`MAPPING_ERROR`, `IDOC_FAILURE`, `CERT_EXPIRY`) are exercised via curated sample incidents and the golden eval set, since reproducing them live requires additional backend infrastructure beyond this trial tenant.

---

## Technology stack

| Layer | Technology |
|---|---|
| **Agent orchestration** | LangGraph (compiled `StateGraph`, conditional edges, typed shared state) |
| **LLM reasoning** | OpenAI Chat Completions — task-specialized generation + function-calling (agentic diagnosis) |
| **Retrieval / RAG** | ChromaDB (cosine / HNSW) · OpenAI `text-embedding-3-small` · offline hashed fallback |
| **SAP integration** | OData v2 · OAuth2 client-credentials (dual-scoped: read + deploy) · CSRF handshake · media-link entity resolution |
| **Service layer** | FastAPI · Pydantic-validated I/O · SAP Fiori-inspired dashboard |
| **Quality** | pytest · a 20-case evaluation harness · deterministic offline mock mode · Docker |

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
python -m evals.run           # 4. (optional) score against the labeled golden set
```

### Connect a live SAP CPI tenant

Ingestion/monitoring credentials:
```
CPI_TOKEN_URL=https://<tenant>.authentication.<region>.hana.ondemand.com/oauth/token
CPI_CLIENT_ID=...
CPI_CLIENT_SECRET=...
CPI_BASE_URL=https://<tenant>.<region>.hana.ondemand.com/api/v1
```

```bash
python -m connectors.sap_cpi   # ingest genuinely-failed messages → data/live_incidents.json
```

Optionally, a second, deploy-capable service key (`WorkspaceArtifactsDeploy` role) unlocks the executor:
```
CPI_DEPLOY_TOKEN_URL=...
CPI_DEPLOY_CLIENT_ID=...
CPI_DEPLOY_CLIENT_SECRET=...
CPI_DEPLOY_BASE_URL=...
```

---

## Project structure

```
agents/         # monitor · diagnosis (agentic) · remediation · executor · reporting
agents/tools.py # tools the diagnosis agent can call (KB search, live deployment/failure lookups)
orchestrator/   # LangGraph state graph + typed shared state
rag/            # ingestion, retrieval, pluggable embedding strategies (ChromaDB)
connectors/     # live SAP CPI OData ingestion, error-taxonomy classification, deploy operations
api/            # FastAPI service (/resolve, /execute, /feedback) + Fiori-inspired dashboard
data/           # sample incidents · live incidents · knowledge base · action map
evals/          # golden labeled incident set + scoring harness
tests/          # pytest suite (hermetic, offline)
```

## Roadmap

- [ ] Widen the executor's action allowlist as more safe, reversible CPI operations are identified
- [ ] LLM-as-judge scoring for the free-text postmortem quality (evals currently score structured fields only)
- [ ] Slack / MS Teams escalation integration
- [ ] Knowledge-base expansion from real historical incident tickets

## Author

**Venkatesh Mudaliar** — SAP BTP/CPI Consultant · AI/ML Engineer
[LinkedIn](https://linkedin.com/in/venkateshcmudaliar) · [GitHub](https://github.com/Venkyyy98)
