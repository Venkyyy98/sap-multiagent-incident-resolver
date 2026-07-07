"""Deterministic tests for the background poller's guard conditions. Doesn't run the actual
timed loop (that's an infinite asyncio loop) — just the checks that decide whether it starts."""
import asyncio
from api import poller
from config import settings


def test_poll_loop_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "poll_enabled", False)
    poller.status["last_error"] = None
    asyncio.run(poller.poll_loop())
    assert "disabled" in poller.status["last_error"].lower()


def test_poll_loop_skips_when_no_credentials(monkeypatch):
    monkeypatch.setattr(settings, "poll_enabled", True)
    monkeypatch.setattr("connectors.sap_cpi.TOKEN_URL", "")
    monkeypatch.setattr("connectors.sap_cpi.CLIENT_ID", "")
    monkeypatch.setattr("connectors.sap_cpi.CLIENT_SECRET", "")
    monkeypatch.setattr("connectors.sap_cpi.BASE_URL", "")
    poller.status["last_error"] = None
    asyncio.run(poller.poll_loop())
    assert "credentials" in poller.status["last_error"].lower()
