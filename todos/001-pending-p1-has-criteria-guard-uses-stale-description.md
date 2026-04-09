---
status: pending
priority: p1
issue_id: "001"
tags: [code-review, quality, correctness]
dependencies: []
---

# has_criteria guard uses raw description instead of effective match description

## Problem Statement

`compute_forecast_actual` computes `has_criteria` before calling `_effective_match_description`, using `forecast.description` directly. If `forecast.description` is `None` but `forecast.recurrence.base_description` is set, `has_criteria` will be `False` and the function returns early with `Decimal("0")` — even though a valid `match_desc` could be constructed. The two checks are semantically out of sync.

## Findings

- **Location:** `bud/services/forecasts.py`, around line 90
- Current code:
  ```python
  has_criteria = forecast.description or forecast.category_id or forecast.tags
  if not has_criteria:
      return Decimal("0")
  match_desc = _effective_match_description(forecast)
  ```
- Flagged by: kieran-python-reviewer (medium severity, fix before merge) and architecture-strategist (latent correctness bug)

## Proposed Solutions

### Option A: Reorder — compute match_desc first (Recommended)
Move `_effective_match_description` before the guard and use `match_desc` in `has_criteria`:
```python
match_desc = _effective_match_description(forecast)
has_criteria = match_desc or forecast.category_id or forecast.tags
if not has_criteria:
    return Decimal("0")
```
**Pros:** Correct, minimal change, consistent  
**Cons:** None  
**Effort:** Small  **Risk:** Low

## Acceptance Criteria
- [ ] `has_criteria` uses `match_desc` (result of `_effective_match_description`) not `forecast.description`
- [ ] All 497 tests continue to pass
- [ ] An installment forecast with `forecast.description=None` and `recurrence.base_description` set is not incorrectly skipped

## Work Log
- 2026-04-09: Identified during ce-review of PR #42
