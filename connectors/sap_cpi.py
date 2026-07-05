"""Optional: pull real failed messages from your SAP CPI tenant instead of sample_incidents.json.

Setup (SAP BTP Cockpit):
1. Integration Suite → your subaccount → Instances/Subscriptions → create a Process Integration
   Runtime service key (or reuse existing) → note clientid, clientsecret, tokenurl.
2. Add to .env:
   CPI_TOKEN_URL=https://<tenant>.authentication.<region>.hana.ondemand.com/oauth/token
   CPI_CLIENT_ID=...
   CPI_CLIENT_SECRET=...
   CPI_BASE_URL=https://<tenant>.<region>.hana.ondemand.com/api/v1
3. python -m connectors.sap_cpi   # fetches failed MessageProcessingLogs → data/live_incidents.json
4. In run_pipeline.py, point Path("data/sample_incidents.json") to "data/live_incidents.json"

Docs: https://api.sap.com/api/MessageProcessingLogs/overview
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = os.getenv("CPI_TOKEN_URL", "")
CLIENT_ID = os.getenv("CPI_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CPI_CLIENT_SECRET", "")
BASE_URL = os.getenv("CPI_BASE_URL", "")


def get_token() -> str:
    resp = requests.post(TOKEN_URL, data={"grant_type": "client_credentials"},
                          auth=(CLIENT_ID, CLIENT_SECRET), timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_error_message(guid: str, token: str) -> str:
    """Fetches the actual exception text for a failed message (a media-link entity, not a plain field)."""
    url = f"{BASE_URL}/MessageProcessingLogs('{guid}')/ErrorInformation/$value"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code != 200 or not resp.text.strip():
        return "No error text available"
    return resp.text.strip()


def classify_error_type(message: str) -> str:
    """Maps raw error text to the KB's failure categories (CPI's LogLevel is just a severity, not a category)."""
    msg = message.lower()
    if "invalid_client" in msg or "unauthorized" in msg or "status code:401" in msg:
        return "AUTH_FAILURE"
    if "timeout" in msg or "timed out" in msg or "remotely closed" in msg:
        return "HTTP_TIMEOUT"
    if "mapping" in msg or "cast" in msg or "xsd:date" in msg:
        return "MAPPING_ERROR"
    if "idoc" in msg or "partner profile" in msg or "we20" in msg:
        return "IDOC_FAILURE"
    if "certificate" in msg or "known_hosts" in msg or "ssh" in msg:
        return "CERT_EXPIRY"
    return "UNKNOWN"


def fetch_failed_messages(top: int = 20) -> list[dict]:
    """Pulls failed MessageProcessingLogs and maps them to our internal incident schema."""
    token = get_token()
    url = f"{BASE_URL}/MessageProcessingLogs?$filter=Status eq 'FAILED'&$top={top}&$format=json"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    raw = resp.json()["d"]["results"]

    incidents = []
    for m in raw:
        message = fetch_error_message(m["MessageGuid"], token)
        incidents.append({
            "incident_id": m["MessageGuid"],
            "iflow": m["IntegrationFlowName"],
            "timestamp": m["LogEnd"],
            "error_type": classify_error_type(message),
            "message": message,
            "payload_size_kb": 0,
            "retry_count": 0,
            "severity": "P1" if m.get("Status") == "FAILED" else "P2",
        })
    return incidents


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    missing = [k for k, v in {"CPI_TOKEN_URL": TOKEN_URL, "CPI_CLIENT_ID": CLIENT_ID,
                              "CPI_CLIENT_SECRET": CLIENT_SECRET, "CPI_BASE_URL": BASE_URL}.items() if not v]
    if missing:
        print(f"ERROR: missing required .env values: {', '.join(missing)}")
        print("Set these in .env (see the module docstring at the top of this file), then re-run.")
        sys.exit(1)

    try:
        data = fetch_failed_messages()
    except requests.exceptions.Timeout:
        print("ERROR: SAP CPI request timed out. Check your network and that the tenant is reachable.")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"ERROR: could not connect to SAP CPI at {BASE_URL}. Check CPI_BASE_URL and your network.")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        if code in (401, 403):
            print(f"ERROR: authentication failed ({code}). Your CPI client credentials may be wrong or expired.")
        else:
            print(f"ERROR: SAP CPI returned HTTP {code}. Response: {e.response.text[:300] if e.response is not None else ''}")
        sys.exit(1)

    Path("data/live_incidents.json").write_text(json.dumps(data, indent=2))
    print(f"Pulled {len(data)} live incidents from SAP CPI → data/live_incidents.json")
