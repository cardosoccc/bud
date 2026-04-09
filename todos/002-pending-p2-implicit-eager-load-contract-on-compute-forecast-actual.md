---
status: pending
priority: p2
issue_id: "002"
tags: [code-review, architecture, sqlalchemy]
dependencies: []
---

# Implicit eager-load contract on compute_forecast_actual is invisible

## Problem Statement

`compute_forecast_actual` is a sync function that now accesses `forecast.recurrence` via `_effective_match_description`. This requires the relationship to be eagerly loaded before the call. If a future call site forgets `selectinload(Forecast.recurrence)`, SQLAlchemy async will raise `MissingGreenlet` at runtime. The contract is invisible from the function signature.

## Findings

- **Location:** `bud/services/forecasts.py`, `compute_forecast_actual` and `_effective_match_description`
- Currently there are 3 call sites, all now correctly eager-loading recurrence (PR #42 fixed the missing one in `_calculate_accumulated_remaining`). But the next call site added will have no warning.
- Flagged by: architecture-strategist, performance-oracle

## Proposed Solutions

### Option A: Add docstring warning (Quick, low risk)
Add a clear note to `compute_forecast_actual` and `_effective_match_description`:
```python
# NOTE: forecast.recurrence must be eagerly loaded before calling this.
# In async SQLAlchemy, lazy-loading this relationship raises MissingGreenlet.
```
**Effort:** Small  **Risk:** Low

### Option B: Pass match_description as an optional parameter (Recommended for long-term)
```python
def compute_forecast_actual(
    forecast: Forecast,
    transactions: list[Transaction],
    *,
    match_description: str | None = None,
) -> Decimal:
    match_desc = match_description if match_description is not None else forecast.description
```
Callers with loaded recurrence compute and pass the resolved description. Keeps sync helper free of ORM traversal.  
**Effort:** Medium  **Risk:** Low

### Option C: Add a `get_forecast_with_recurrence` service helper
Add a targeted single-record query with `selectinload` to prevent future callers from using bare `get_forecast` and then calling `compute_forecast_actual`.  
**Effort:** Small  **Risk:** Low

## Acceptance Criteria
- [ ] Future developers cannot silently break matching by omitting selectinload
- [ ] Contract is visible at the call site or documented

## Work Log
- 2026-04-09: Identified during ce-review of PR #42
