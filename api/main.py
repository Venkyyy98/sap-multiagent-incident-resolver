"""FastAPI service exposing the multi-agent pipeline."""
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from orchestrator.graph import pipeline
from agents.executor import execute_mitigation
from config import settings

app = FastAPI(title="SAP IntelliOps — Multi-Agent Incident Resolver")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def dashboard():
    return FileResponse("static/index.html")


class Incident(BaseModel):
    incident_id: str
    iflow: str
    timestamp: str
    error_type: str
    message: str
    payload_size_kb: int = 0
    retry_count: int = 0
    severity: str = "P2"


@app.post("/resolve")
def resolve(incident: Incident):
    try:
        result = pipeline.invoke({"incident": incident.model_dump(), "log": []})
    except Exception as e:
        # Never surface a raw 500 to the dashboard — return a structured, human-readable failure
        return JSONResponse(status_code=200, content={
            "incident_id": incident.incident_id,
            "error": f"Pipeline failed: {type(e).__name__}: {e}",
            "priority_score": 0,
            "diagnosis": {"root_cause": "Pipeline error — see error field", "confidence": 0.0},
            "remediation": {"action": "ESCALATE", "steps": ["Pipeline failed — manual review required"], "risk": "HIGH"},
            "auto_approved": False,
            "needs_human": True,
            "report": None,
            "report_markdown": "",
            "trace": [f"[Error] {type(e).__name__}: {e}"],
        })
    return {
        "incident_id": incident.incident_id,
        "priority_score": result["priority_score"],
        "diagnosis": result["diagnosis"],
        "remediation": result["remediation"],
        "auto_approved": result["approved"],
        "needs_human": result["needs_human"],
        "auto_action": result.get("auto_action", {"triggered": False}),
        "report": result["report_path"],
        "report_markdown": Path(result["report_path"]).read_text(),
        "trace": result["log"],
    }


class ExecuteRequest(BaseModel):
    incident_id: str
    iflow: str
    action: str
    confidence: float
    risk: str
    auto_approved: bool


@app.post("/execute")
def execute(req: ExecuteRequest):
    # Never trust the client alone for something this consequential — re-check the gate server-side.
    if not (req.auto_approved and req.risk == "LOW" and req.confidence >= settings.confidence_threshold):
        return JSONResponse(status_code=200, content={
            "executed": False,
            "outcome": "NOT_ELIGIBLE",
            "detail": "Execution requires auto-approved status, LOW risk, and confidence at or above the "
                      f"threshold ({settings.confidence_threshold}). This incident doesn't qualify — a human must act on it.",
        })
    # Re-derive the execution type from the action map server-side rather than trusting the caller —
    # the client cannot talk us into a STOP/REDEPLOY the action isn't actually mapped to.
    action_map = json.loads(Path("data/action_map.json").read_text())
    execution_type = action_map.get(req.action, {}).get("execution_type", "NONE")
    try:
        return execute_mitigation(req.iflow, req.incident_id, execution_type)
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "executed": False, "outcome": "ERROR", "detail": f"{type(e).__name__}: {e}",
        })


class Feedback(BaseModel):
    incident_id: str
    error_type: str
    message: str
    root_cause: str
    action_code: str
    steps: list[str]
    execution_type: str = "NONE"  # freshly-taught actions are recommend-only unless explicitly marked STOP/REDEPLOY


@app.post("/feedback")
def feedback(fb: Feedback):
    """Human confirms the real root cause + fix for an escalated incident. Writes it back into the
    knowledge base (both the JSON source of truth and the live ChromaDB collection), so the *next*
    incident of this kind is recognized with high confidence instead of being escalated again."""
    from rag.ingest import get_collection

    kb_path = Path("data/knowledge_base.json")
    kb = json.loads(kb_path.read_text())
    new_id = f"KB-TAUGHT-{fb.incident_id[:8]}"
    kb = [d for d in kb if d["id"] != new_id]  # replace if re-taught
    text = f"{fb.root_cause} {fb.message}"[:600]
    kb.append({"id": new_id, "error_type": fb.error_type, "text": text, "resolution": fb.action_code})
    kb_path.write_text(json.dumps(kb, indent=2))

    action_map_path = Path("data/action_map.json")
    action_map = json.loads(action_map_path.read_text()) if action_map_path.exists() else {}
    action_map[fb.action_code] = {"execution_type": fb.execution_type, "steps": fb.steps}
    action_map_path.write_text(json.dumps(action_map, indent=2))

    col = get_collection()
    col.upsert(ids=[new_id], documents=[text],
               metadatas=[{"error_type": fb.error_type, "resolution": fb.action_code}])

    return {"taught": True, "kb_id": new_id, "detail": f"Learned '{fb.action_code}' for {fb.error_type} incidents. Re-run this incident to see it applied."}


@app.get("/incidents/sample")
def sample_incidents():
    return json.loads(Path("data/sample_incidents.json").read_text())


@app.get("/incidents/live")
def live_incidents():
    path = Path("data/live_incidents.json")
    if not path.exists():
        return []
    return json.loads(path.read_text())


@app.get("/health")
def health():
    return {"status": "ok"}
