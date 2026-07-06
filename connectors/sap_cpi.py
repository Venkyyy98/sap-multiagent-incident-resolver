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

# Separate, deploy-capable service key (WorkspaceArtifactsDeploy/NodeManager.deploycontent scopes).
# The read-only key above cannot deploy — see connectors/sap_cpi.py history / README for why these
# are deliberately two different credentials rather than one over-privileged one.
DEPLOY_TOKEN_URL = os.getenv("CPI_DEPLOY_TOKEN_URL", "")
DEPLOY_CLIENT_ID = os.getenv("CPI_DEPLOY_CLIENT_ID", "")
DEPLOY_CLIENT_SECRET = os.getenv("CPI_DEPLOY_CLIENT_SECRET", "")
DEPLOY_BASE_URL = os.getenv("CPI_DEPLOY_BASE_URL", "")


def get_token() -> str:
    resp = requests.post(TOKEN_URL, data={"grant_type": "client_credentials"},
                          auth=(CLIENT_ID, CLIENT_SECRET), timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def deploy_capable() -> bool:
    return bool(DEPLOY_TOKEN_URL and DEPLOY_CLIENT_ID and DEPLOY_CLIENT_SECRET and DEPLOY_BASE_URL)


def get_deploy_token() -> str:
    resp = requests.post(DEPLOY_TOKEN_URL, data={"grant_type": "client_credentials"},
                          auth=(DEPLOY_CLIENT_ID, DEPLOY_CLIENT_SECRET), timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_runtime_status(iflow_id: str) -> dict:
    """Reads current deployment status of an iFlow (works with either credential set)."""
    token = get_deploy_token() if deploy_capable() else get_token()
    resp = requests.get(f"{DEPLOY_BASE_URL or BASE_URL}/IntegrationRuntimeArtifacts('{iflow_id}')",
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    return resp.json()["d"]


def redeploy_iflow(iflow_id: str) -> str:
    """Redeploys (restarts) an iFlow. Requires the deploy-capable credential. Returns the async task id."""
    if not deploy_capable():
        raise RuntimeError("No deploy-capable credential configured (CPI_DEPLOY_CLIENT_ID/SECRET missing in .env)")
    token = get_deploy_token()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
    csrf_resp = s.get(f"{DEPLOY_BASE_URL}/", headers={"X-CSRF-Token": "Fetch"}, timeout=30)
    csrf = csrf_resp.headers.get("x-csrf-token", "")
    resp = s.post(f"{DEPLOY_BASE_URL}/DeployIntegrationDesigntimeArtifact?Id='{iflow_id}'&Version='active'",
                  headers={"X-CSRF-Token": csrf}, timeout=60)
    resp.raise_for_status()
    return resp.text.strip()


def poll_until_started(iflow_id: str, timeout_s: int = 180, interval_s: int = 10) -> dict:
    """Polls runtime status until STARTED or timeout. Returns the final status dict."""
    import time
    elapsed = 0
    last = {}
    while elapsed <= timeout_s:
        last = get_runtime_status(iflow_id)
        if last.get("Status") == "STARTED":
            return last
        time.sleep(interval_s)
        elapsed += interval_s
    return last


def stop_iflow(iflow_id: str) -> None:
    """Stops (undeploys) a running iFlow so it processes no further messages — the correct mitigation
    when leaving it running actively causes damage (bad-payload creating wrong records, an expired
    cert/credential that will just keep failing). Requires the deploy-capable credential. Reversible:
    a human fixes the root cause and redeploys."""
    if not deploy_capable():
        raise RuntimeError("No deploy-capable credential configured (CPI_DEPLOY_CLIENT_ID/SECRET missing in .env)")
    token = get_deploy_token()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
    csrf = s.get(f"{DEPLOY_BASE_URL}/", headers={"X-CSRF-Token": "Fetch"}, timeout=30).headers.get("x-csrf-token", "")
    resp = s.delete(f"{DEPLOY_BASE_URL}/IntegrationRuntimeArtifacts('{iflow_id}')",
                    headers={"X-CSRF-Token": csrf}, timeout=60)
    resp.raise_for_status()


def is_stopped(iflow_id: str) -> bool:
    """True once the iFlow is no longer deployed to the runtime (a 404 on the runtime artifact)."""
    token = get_deploy_token() if deploy_capable() else get_token()
    resp = requests.get(f"{DEPLOY_BASE_URL or BASE_URL}/IntegrationRuntimeArtifacts('{iflow_id}')",
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=30)
    return resp.status_code == 404


def poll_until_stopped(iflow_id: str, timeout_s: int = 60, interval_s: int = 5) -> bool:
    """Polls until the iFlow is undeployed (stop confirmed) or timeout."""
    import time
    elapsed = 0
    while elapsed <= timeout_s:
        if is_stopped(iflow_id):
            return True
        time.sleep(interval_s)
        elapsed += interval_s
    return is_stopped(iflow_id)


def failures_since(iflow_id: str, since_iso: str) -> list[dict]:
    """Checks MessageProcessingLogs for new FAILED entries on this iFlow since a given time (verification signal)."""
    token = get_deploy_token() if deploy_capable() else get_token()
    url = (f"{DEPLOY_BASE_URL or BASE_URL}/MessageProcessingLogs"
           f"?$filter=IntegrationFlowName eq '{iflow_id}' and Status eq 'FAILED' and LogEnd gt datetime'{since_iso}'"
           f"&$format=json")
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json()["d"]["results"]


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
