"""Deterministic tests for the autonomous circuit-breaker gate. No live network — the tenant
calls (failure count, stop) are monkeypatched, so these exercise only the trip logic."""
from agents.circuit_breaker import circuit_breaker_agent
from config import settings


def _state(execution_type="STOP", approved=True):
    return {
        "enriched": {"iflow": "Some-Flow", "incident_id": "X"},
        "remediation": {"action": "ROTATE_CREDENTIALS", "execution_type": execution_type, "risk": "LOW"},
        "approved": approved,
        "log": [],
    }


def test_breaker_trips_when_failures_exceed_threshold(monkeypatch):
    monkeypatch.setattr(settings, "auto_stop_enabled", True)
    monkeypatch.setattr(settings, "auto_stop_failure_threshold", 3)
    monkeypatch.setattr("connectors.sap_cpi.recent_failure_count", lambda iflow, hours=24: 5)
    monkeypatch.setattr("connectors.sap_cpi.deploy_capable", lambda: True)
    stopped_calls = []
    monkeypatch.setattr("connectors.sap_cpi.stop_iflow", lambda iflow: stopped_calls.append(iflow))
    monkeypatch.setattr("connectors.sap_cpi.poll_until_stopped", lambda iflow, **kw: True)

    out = circuit_breaker_agent(_state())
    assert out["auto_action"]["triggered"] is True
    assert out["auto_action"]["success"] is True
    assert out["auto_action"]["failure_count"] == 5
    assert stopped_calls == ["Some-Flow"]  # the flow was actually stopped


def test_breaker_holds_below_threshold(monkeypatch):
    monkeypatch.setattr(settings, "auto_stop_enabled", True)
    monkeypatch.setattr(settings, "auto_stop_failure_threshold", 3)
    monkeypatch.setattr("connectors.sap_cpi.recent_failure_count", lambda iflow, hours=24: 1)
    stopped_calls = []
    monkeypatch.setattr("connectors.sap_cpi.stop_iflow", lambda iflow: stopped_calls.append(iflow))

    out = circuit_breaker_agent(_state())
    assert out["auto_action"]["triggered"] is False
    assert stopped_calls == []  # a single failure must NOT trip the breaker


def test_breaker_ignores_non_stop_actions(monkeypatch):
    monkeypatch.setattr(settings, "auto_stop_enabled", True)
    monkeypatch.setattr(settings, "auto_stop_failure_threshold", 1)
    stopped_calls = []
    monkeypatch.setattr("connectors.sap_cpi.stop_iflow", lambda iflow: stopped_calls.append(iflow))

    out = circuit_breaker_agent(_state(execution_type="REDEPLOY"))
    assert out["auto_action"]["triggered"] is False
    assert stopped_calls == []  # a redeploy-type remediation is never auto-stopped


def test_breaker_respects_disable_flag(monkeypatch):
    monkeypatch.setattr(settings, "auto_stop_enabled", False)
    monkeypatch.setattr("connectors.sap_cpi.recent_failure_count", lambda iflow, hours=24: 99)
    stopped_calls = []
    monkeypatch.setattr("connectors.sap_cpi.stop_iflow", lambda iflow: stopped_calls.append(iflow))

    out = circuit_breaker_agent(_state())
    assert out["auto_action"]["triggered"] is False
    assert stopped_calls == []  # disabled → never actuates, no matter how many failures
