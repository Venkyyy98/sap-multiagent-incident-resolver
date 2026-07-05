"""FastAPI service exposing the multi-agent pipeline."""
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from orchestrator.graph import pipeline

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
    result = pipeline.invoke({"incident": incident.model_dump(), "log": []})
    return {
        "incident_id": incident.incident_id,
        "priority_score": result["priority_score"],
        "diagnosis": result["diagnosis"],
        "remediation": result["remediation"],
        "auto_approved": result["approved"],
        "needs_human": result["needs_human"],
        "report": result["report_path"],
        "report_markdown": Path(result["report_path"]).read_text(),
        "trace": result["log"],
    }


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
