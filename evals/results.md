# Evaluation Results

Run over 20 golden incidents (golden_incidents.json).

| Metric | Score |
|---|---|
| Taxonomy classification accuracy | 100.0% (20/20) |
| Remediation action accuracy (known-pattern cases only) | 100.0% (16/16) |
| Escalation-gate precision | 1.00 |
| Escalation-gate recall | 1.00 |
| Escalation-gate F1 | 1.00 |

Escalation gate: "positive" = incident *should* be escalated to a human (novel pattern, no
KB precedent). Precision/recall are computed against that label — recall matters most here,
since a false negative (an incident that should escalate but got auto-approved instead) is
the dangerous failure mode; a false positive (escalating something that could've been
auto-approved) just costs a human a few minutes of unnecessary review.

## Per-incident detail

| Incident | Expected type | Predicted type | ✓ | Expected action | Predicted action | ✓ | Expected escalate | Actual escalate | ✓ | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|
| EVAL-001 | HTTP_TIMEOUT | HTTP_TIMEOUT | ✅ | ENABLE_PAGINATION | ENABLE_PAGINATION | ✅ | False | False | ✅ | 0.88 |
| EVAL-002 | HTTP_TIMEOUT | HTTP_TIMEOUT | ✅ | ENABLE_PAGINATION | ENABLE_PAGINATION | ✅ | False | False | ✅ | 0.88 |
| EVAL-003 | HTTP_TIMEOUT | HTTP_TIMEOUT | ✅ | ASYNC_DECOUPLE | ASYNC_DECOUPLE | ✅ | False | False | ✅ | 0.88 |
| EVAL-004 | HTTP_TIMEOUT | HTTP_TIMEOUT | ✅ | ASYNC_DECOUPLE | ASYNC_DECOUPLE | ✅ | False | False | ✅ | 0.88 |
| EVAL-005 | AUTH_FAILURE | AUTH_FAILURE | ✅ | ROTATE_CREDENTIALS | ROTATE_CREDENTIALS | ✅ | False | False | ✅ | 0.90 |
| EVAL-006 | AUTH_FAILURE | AUTH_FAILURE | ✅ | ROTATE_CREDENTIALS | ROTATE_CREDENTIALS | ✅ | False | False | ✅ | 0.90 |
| EVAL-007 | AUTH_FAILURE | AUTH_FAILURE | ✅ | ROTATE_CREDENTIALS | ROTATE_CREDENTIALS | ✅ | False | False | ✅ | 0.88 |
| EVAL-008 | AUTH_FAILURE | AUTH_FAILURE | ✅ | ROTATE_CREDENTIALS | ROTATE_CREDENTIALS | ✅ | False | False | ✅ | 0.90 |
| EVAL-009 | MAPPING_ERROR | MAPPING_ERROR | ✅ | PATCH_MAPPING | PATCH_MAPPING | ✅ | False | False | ✅ | 0.88 |
| EVAL-010 | MAPPING_ERROR | MAPPING_ERROR | ✅ | PATCH_MAPPING | PATCH_MAPPING | ✅ | False | False | ✅ | 0.90 |
| EVAL-011 | MAPPING_ERROR | MAPPING_ERROR | ✅ | PATCH_MAPPING | PATCH_MAPPING | ✅ | False | False | ✅ | 0.88 |
| EVAL-012 | IDOC_FAILURE | IDOC_FAILURE | ✅ | ESCALATE_TO_BASIS | ESCALATE_TO_BASIS | ✅ | False | False | ✅ | 0.88 |
| EVAL-013 | IDOC_FAILURE | IDOC_FAILURE | ✅ | ESCALATE_TO_BASIS | ESCALATE_TO_BASIS | ✅ | False | False | ✅ | 0.88 |
| EVAL-014 | CERT_EXPIRY | CERT_EXPIRY | ✅ | UPDATE_KEYSTORE | UPDATE_KEYSTORE | ✅ | False | False | ✅ | 0.90 |
| EVAL-015 | CERT_EXPIRY | CERT_EXPIRY | ✅ | UPDATE_KEYSTORE | UPDATE_KEYSTORE | ✅ | False | False | ✅ | 0.88 |
| EVAL-016 | UNKNOWN | UNKNOWN | ✅ | — | Investigate and fix the null handling in the Groovy script | ✅ | True | True | ✅ | 0.60 |
| EVAL-017 | UNKNOWN | UNKNOWN | ✅ | — | Investigate and Report | ✅ | True | True | ✅ | 0.60 |
| EVAL-018 | UNKNOWN | UNKNOWN | ✅ | — | Investigate and resolve the custom ValidationException. | ✅ | True | True | ✅ | 0.60 |
| EVAL-019 | UNKNOWN | UNKNOWN | ✅ | — | Fix the bug in the Groovy script. | ✅ | True | True | ✅ | 0.60 |
| EVAL-020 | AUTH_FAILURE | AUTH_FAILURE | ✅ | ROTATE_CREDENTIALS | ROTATE_CREDENTIALS | ✅ | False | False | ✅ | 0.90 |
