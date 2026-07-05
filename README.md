# SAP IntelliOps — Multi-Agent Incident Resolution System

An AI-powered multi-agent system that autonomously monitors, diagnoses, remediates, and reports on SAP CPI (Cloud Platform Integration) iFlow failures — built with **LangGraph**, **RAG (ChromaDB)**, and **Claude/LLM APIs**.

## Why this project
SAP integration landscapes generate thousands of iFlow errors (OData timeouts, auth failures, mapping errors, IDoc issues). Manual triage is slow. This system uses **4 specialized AI agents orchestrated as a graph** to cut mean-time-to-resolution.

## Architecture

```
                ┌──────────────────────────────────────────┐
                │            LangGraph Orchestrator         │
                └──────────────────────────────────────────┘
 Incident ──▶ Monitor Agent ──▶ Diagnosis Agent ──▶ Remediation Agent ──▶ Reporting Agent
              (detect/enrich)    (RAG + LLM root      (action plan,        (postmortem,
                                  cause analysis)      auto-fix/escalate)   notifications)
                                       │
                                       ▼
                               ChromaDB Vector Store
                            (historical incident KB)
```

### Agents
| Agent | Role | Key concepts demonstrated |
|---|---|---|
| **Monitor** | Ingests CPI logs, detects anomalies, enriches context | Event-driven pipelines, structured parsing |
| **Diagnosis** | Root-cause analysis using RAG over historical incidents + LLM reasoning | RAG, embeddings, prompt engineering |
| **Remediation** | Decides fix strategy (retry / restart / reprocess / escalate) with confidence gating | Tool use, human-in-the-loop, guardrails |
| **Reporting** | Generates postmortem + stakeholder summary | LLM summarization, structured output |

### Key AI/ML Engineering concepts covered
- Multi-agent orchestration with **LangGraph** (state machines, conditional edges)
- **RAG** pipeline: chunking, embeddings, vector search (ChromaDB)
- **Human-in-the-loop** gating for low-confidence remediations
- **Structured LLM outputs** (Pydantic validation)
- **Mock LLM mode** for offline testing / CI
- **FastAPI** service layer + REST API
- Unit tests with pytest

## Quickstart

```bash
git clone https://github.com/Venkyyy98/sap-multiagent-incident-resolver.git
cd sap-multiagent-incident-resolver
pip install -r requirements.txt
cp .env.example .env          # add OPENAI_API_KEY (or leave blank for mock mode)

# 1. Build the RAG knowledge base
python -m rag.ingest

# 2. Run the pipeline on sample incidents
python run_pipeline.py

# 3. Start the API + dashboard
uvicorn api.main:app --reload   # http://localhost:8000/docs
```

## Sample output
```
[Monitor]     Detected P1 incident INC-1002: OAuth token failure on iFlow 'SF_EC_to_S4_Employee'
[Diagnosis]   Root cause: expired client credentials (confidence 0.91) — matched 3 similar past incidents
[Remediation] Action: ROTATE_CREDENTIALS + RETRY | auto-approved (confidence > 0.85)
[Reporting]   Postmortem written to reports/INC-1002.md
```

## Tech stack
Python 3.11 · LangGraph · OpenAI API · ChromaDB · FastAPI · Pydantic · pytest · Docker

## Project structure
```
agents/         # 4 specialized agents
orchestrator/   # LangGraph state graph wiring
rag/            # ingestion + retrieval (ChromaDB)
api/            # FastAPI service
data/           # sample CPI incident logs + knowledge base
tests/          # pytest suite
```

## Roadmap
- [ ] Live SAP CPI OData API connector (replace sample logs)
- [ ] Agent evaluation harness (LLM-as-judge)
- [ ] Slack/Teams notification integration
- [ ] Fine-tuned classifier for error categorization

## Author
**Venkatesh Mudaliar** — SAP BTP/CPI Consultant | AI/ML Engineer
[LinkedIn](https://linkedin.com/in/venkateshcmudaliar) · [GitHub](https://github.com/Venkyyy98)
