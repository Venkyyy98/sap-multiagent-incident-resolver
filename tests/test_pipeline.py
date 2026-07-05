import json
from pathlib import Path
from agents.monitor import monitor_agent
from orchestrator.graph import pipeline

SAMPLE = json.loads(Path("data/sample_incidents.json").read_text())

def test_monitor_scores_p1_higher():
    p1 = monitor_agent({"incident": SAMPLE[1], "log": []})
    assert p1["priority_score"] > 0.6
    assert "business_impact" in p1["enriched"]

def test_full_pipeline_auth_failure():
    result = pipeline.invoke({"incident": SAMPLE[1], "log": []})
    assert result["diagnosis"]["confidence"] > 0
    assert result["remediation"]["action"]
    assert result["report_path"]

def test_human_gate_exists():
    result = pipeline.invoke({"incident": SAMPLE[3], "log": []})
    assert isinstance(result["needs_human"], bool)
