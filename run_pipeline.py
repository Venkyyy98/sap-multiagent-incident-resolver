"""Entry point: run the multi-agent pipeline over all sample incidents."""
import json
from pathlib import Path
from orchestrator.graph import pipeline

def main():
    incidents = json.loads(Path("data/live_incidents.json").read_text())
    print(f"Processing {len(incidents)} incidents through the multi-agent pipeline\n" + "=" * 70)
    for inc in incidents:
        result = pipeline.invoke({"incident": inc, "log": []})
        print("\n".join(result["log"]) + "\n" + "-" * 70)

if __name__ == "__main__":
    main()
