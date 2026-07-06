"""Fast, deterministic tests for the executor allowlist gate and /execute endpoint.
No live network calls — these only exercise the gating logic, not the actual redeploy."""
from fastapi.testclient import TestClient
from api.main import app
from agents.executor import execute_mitigation
from connectors.sap_cpi import classify_error_type

client = TestClient(app)


def test_execute_rejects_low_confidence():
    resp = client.post("/execute", json={
        "incident_id": "X", "iflow": "Some-Flow", "action": "ROTATE_CREDENTIALS",
        "confidence": 0.5, "risk": "LOW", "auto_approved": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["executed"] is False
    assert body["outcome"] == "NOT_ELIGIBLE"


def test_execute_rejects_non_low_risk():
    resp = client.post("/execute", json={
        "incident_id": "X", "iflow": "Some-Flow", "action": "ROTATE_CREDENTIALS",
        "confidence": 0.95, "risk": "MEDIUM", "auto_approved": True,
    })
    assert resp.json()["outcome"] == "NOT_ELIGIBLE"


def test_execute_rejects_when_not_auto_approved():
    resp = client.post("/execute", json={
        "incident_id": "X", "iflow": "Some-Flow", "action": "ROTATE_CREDENTIALS",
        "confidence": 0.95, "risk": "LOW", "auto_approved": False,
    })
    assert resp.json()["outcome"] == "NOT_ELIGIBLE"


def test_executor_reports_not_executable_without_deploy_credentials(monkeypatch):
    monkeypatch.setattr("connectors.sap_cpi.deploy_capable", lambda: False)
    result = execute_mitigation("Some-Flow", "X", "STOP")
    assert result["executed"] is False
    assert result["outcome"] == "NOT_EXECUTABLE"


def test_recommend_only_action_is_not_auto_executed(monkeypatch):
    # An action mapped to execution_type NONE (e.g. ESCALATE_TO_BASIS) must never actuate the tenant.
    monkeypatch.setattr("connectors.sap_cpi.deploy_capable", lambda: True)
    result = execute_mitigation("Some-Flow", "X", "NONE")
    assert result["executed"] is False
    assert result["outcome"] == "RECOMMEND_ONLY"


def test_action_map_execution_types_are_valid():
    # Guard the data contract: every action's execution_type is one the executor understands,
    # and the high-judgment actions are never auto-executable.
    import json
    from pathlib import Path
    action_map = json.loads(Path("data/action_map.json").read_text())
    for code, entry in action_map.items():
        assert entry["execution_type"] in {"STOP", "REDEPLOY", "NONE"}, code
    assert action_map["ESCALATE_TO_BASIS"]["execution_type"] == "NONE"
    assert action_map["ROTATE_CREDENTIALS"]["execution_type"] == "STOP"


def test_classify_error_type_covers_known_categories():
    assert classify_error_type("401 invalid_client bad credentials") == "AUTH_FAILURE"
    assert classify_error_type("Read timed out after 60000ms") == "HTTP_TIMEOUT"
    assert classify_error_type("Remotely closed") == "HTTP_TIMEOUT"
    assert classify_error_type("cannot cast to xsd:date") == "MAPPING_ERROR"
    assert classify_error_type("IDoc partner profile not found") == "IDOC_FAILURE"
    assert classify_error_type("SSH known_hosts certificate expired") == "CERT_EXPIRY"
    assert classify_error_type("something never seen before") == "UNKNOWN"
