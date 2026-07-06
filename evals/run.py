"""Evaluation harness: runs the pipeline over a golden, labeled incident set and scores
taxonomy classification accuracy, remediation action correctness, and escalation-gate
precision/recall. Writes evals/results.md.

Usage: python -m evals.run
"""
import json
from pathlib import Path
from connectors.sap_cpi import classify_error_type
from orchestrator.graph import pipeline

GOLDEN_PATH = Path(__file__).parent / "golden_incidents.json"
RESULTS_PATH = Path(__file__).parent / "results.md"


def run():
    golden = json.loads(GOLDEN_PATH.read_text())
    rows = []

    for case in golden:
        incident = {k: v for k, v in case.items() if not k.startswith("expected_")}

        predicted_type = classify_error_type(case["message"])
        result = pipeline.invoke({"incident": incident, "log": []})
        predicted_action = result["remediation"]["action"]
        escalated = result["needs_human"]

        rows.append({
            "incident_id": case["incident_id"],
            "expected_type": case["expected_error_type"], "predicted_type": predicted_type,
            "type_correct": predicted_type == case["expected_error_type"],
            "expected_action": case["expected_action"], "predicted_action": predicted_action,
            "action_correct": (case["expected_action"] is None) or (predicted_action == case["expected_action"]),
            "expected_escalate": case["expected_escalate"], "actual_escalate": escalated,
            "confidence": result["diagnosis"]["confidence"],
        })
        print(f"{case['incident_id']}: type={predicted_type} (want {case['expected_error_type']}) | "
              f"action={predicted_action} (want {case['expected_action']}) | "
              f"escalate={escalated} (want {case['expected_escalate']}) | conf={result['diagnosis']['confidence']:.2f}")

    n = len(rows)
    taxonomy_acc = sum(r["type_correct"] for r in rows) / n

    scored_action_rows = [r for r in rows if r["expected_action"] is not None]
    action_acc = sum(r["action_correct"] for r in scored_action_rows) / len(scored_action_rows) if scored_action_rows else float("nan")

    tp = sum(1 for r in rows if r["expected_escalate"] and r["actual_escalate"])
    fp = sum(1 for r in rows if not r["expected_escalate"] and r["actual_escalate"])
    fn = sum(1 for r in rows if r["expected_escalate"] and not r["actual_escalate"])
    tn = sum(1 for r in rows if not r["expected_escalate"] and not r["actual_escalate"])
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) and precision == precision and recall == recall else float("nan")

    summary = f"""# Evaluation Results

Run over {n} golden incidents ({GOLDEN_PATH.name}).

| Metric | Score |
|---|---|
| Taxonomy classification accuracy | {taxonomy_acc:.1%} ({sum(r['type_correct'] for r in rows)}/{n}) |
| Remediation action accuracy (known-pattern cases only) | {action_acc:.1%} ({sum(r['action_correct'] for r in scored_action_rows)}/{len(scored_action_rows)}) |
| Escalation-gate precision | {precision:.2f} |
| Escalation-gate recall | {recall:.2f} |
| Escalation-gate F1 | {f1:.2f} |

Escalation gate: "positive" = incident *should* be escalated to a human (novel pattern, no
KB precedent). Precision/recall are computed against that label — recall matters most here,
since a false negative (an incident that should escalate but got auto-approved instead) is
the dangerous failure mode; a false positive (escalating something that could've been
auto-approved) just costs a human a few minutes of unnecessary review.

## Per-incident detail

| Incident | Expected type | Predicted type | ✓ | Expected action | Predicted action | ✓ | Expected escalate | Actual escalate | ✓ | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|
"""
    for r in rows:
        summary += (f"| {r['incident_id']} | {r['expected_type']} | {r['predicted_type']} | {'✅' if r['type_correct'] else '❌'} | "
                   f"{r['expected_action'] or '—'} | {r['predicted_action']} | {'✅' if r['action_correct'] else '❌'} | "
                   f"{r['expected_escalate']} | {r['actual_escalate']} | {'✅' if r['expected_escalate']==r['actual_escalate'] else '❌'} | "
                   f"{r['confidence']:.2f} |\n")

    RESULTS_PATH.write_text(summary)
    print()
    print(f"Taxonomy accuracy: {taxonomy_acc:.1%} | Action accuracy: {action_acc:.1%} | "
          f"Escalation precision: {precision:.2f} recall: {recall:.2f} F1: {f1:.2f}")
    print(f"Full report written to {RESULTS_PATH}")


if __name__ == "__main__":
    run()
