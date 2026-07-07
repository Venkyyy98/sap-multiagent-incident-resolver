"""Background poller: periodically pulls failed messages from the live SAP CPI tenant into
data/live_incidents.json, so the dashboard reflects new failures without a manual
`python -m connectors.sap_cpi` run. Runs as an asyncio task for the lifetime of the FastAPI app.
"""
import asyncio
import json
import time
from pathlib import Path
from connectors import sap_cpi
from config import settings

LIVE_INCIDENTS_PATH = Path("data/live_incidents.json")

# In-memory status, surfaced via GET /poll/status for the dashboard indicator.
status = {
    "enabled": settings.poll_enabled,
    "interval_seconds": settings.poll_interval_seconds,
    "last_poll_ts": None,
    "last_success_ts": None,
    "last_error": None,
    "incident_count": None,
}


def _cpi_read_configured() -> bool:
    return bool(sap_cpi.TOKEN_URL and sap_cpi.CLIENT_ID and sap_cpi.CLIENT_SECRET and sap_cpi.BASE_URL)


async def poll_loop():
    """Runs forever (until the app shuts down). Never raises — a single failed cycle (tenant
    unreachable, token expired) is logged into `status` and retried next interval, not fatal."""
    if not settings.poll_enabled:
        status["last_error"] = "Polling disabled (POLL_ENABLED=false)"
        return
    if not _cpi_read_configured():
        status["last_error"] = "No CPI read credentials configured in .env — auto-poll idle"
        return

    while True:
        status["last_poll_ts"] = time.time()
        try:
            data = await asyncio.to_thread(sap_cpi.fetch_failed_messages)
            LIVE_INCIDENTS_PATH.write_text(json.dumps(data, indent=2))
            status["last_success_ts"] = time.time()
            status["incident_count"] = len(data)
            status["last_error"] = None
        except Exception as e:
            status["last_error"] = f"{type(e).__name__}: {e}"
        await asyncio.sleep(settings.poll_interval_seconds)
