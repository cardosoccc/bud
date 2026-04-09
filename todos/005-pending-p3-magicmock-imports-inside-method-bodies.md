---
status: pending
priority: p3
issue_id: "005"
tags: [code-review, quality, style]
dependencies: ["003"]
---

# MagicMock imported inside method bodies instead of module level

## Problem Statement

`from unittest.mock import MagicMock` is called inside `_make_forecast`, `_make_transaction`, and repeated in two test method bodies. Python convention is to import at module level. Repeated in-body imports mislead readers into thinking there is a reason for deferral.

## Findings

- **Location:** `tests/test_forecasts_command.py`, class `TestInstallmentMatchDescription`
- Violates PEP 8 import-at-the-top convention
- Also: `test_non_installment_recurrent_forecast_uses_bare_description` and `test_non_recurrent_forecast_uses_stored_description` inline full MagicMock construction instead of calling `_make_forecast`
- Flagged by: kieran-python-reviewer, code-simplicity-reviewer

## Proposed Solutions

### Option A: Hoist import to module level + use _make_forecast consistently
1. Add `from unittest.mock import MagicMock` to module-level imports in the test file
2. Remove per-method imports
3. Update `test_non_installment_recurrent_forecast_uses_bare_description` and `test_non_recurrent_forecast_uses_stored_description` to use `_make_forecast`  
**Effort:** Small  **Risk:** Low

## Acceptance Criteria
- [ ] `MagicMock` imported once at module level
- [ ] No duplicate inline imports in test methods
- [ ] All 5 tests still pass

## Work Log
- 2026-04-09: Identified during ce-review of PR #42. Note: best resolved together with todo #003 (move tests to service file).
