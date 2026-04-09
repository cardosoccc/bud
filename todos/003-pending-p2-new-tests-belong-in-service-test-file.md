---
status: pending
priority: p2
issue_id: "003"
tags: [code-review, quality, testing]
dependencies: []
---

# New installment match tests placed in wrong test file

## Problem Statement

The 5 new `TestInstallmentMatchDescription` tests are pure unit tests of `bud.services.forecasts.compute_forecast_actual`. They live in `tests/test_forecasts_command.py`, which is an integration test file exercising the Click command layer against a real async database. This misplacement causes confusion and makes the test file harder to navigate as the suite grows.

## Findings

- **Location:** `tests/test_forecasts_command.py`, class `TestInstallmentMatchDescription`
- Uses `MagicMock` — no DB, no CLI layer. Pure service unit test.
- `tests/test_forecasts_service.py` already exists and is the correct home for service-layer tests.
- Flagged by: architecture-strategist

## Proposed Solutions

### Option A: Move tests to test_forecasts_service.py (Recommended)
Move `TestInstallmentMatchDescription` to `tests/test_forecasts_service.py`. Also move the `MagicMock` import to module level.  
**Effort:** Small  **Risk:** Low

### Option B: Create tests/test_forecasts_matching.py
A dedicated file for matching logic tests, colocated with related service tests.  
**Effort:** Small  **Risk:** Low

## Acceptance Criteria
- [ ] `TestInstallmentMatchDescription` lives in a service-layer test file (not a command test file)
- [ ] All 5 tests still pass
- [ ] `MagicMock` import is at module level

## Work Log
- 2026-04-09: Identified during ce-review of PR #42
