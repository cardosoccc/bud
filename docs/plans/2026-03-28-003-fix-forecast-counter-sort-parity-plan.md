---
title: "fix: Forecast counter resolution uses same sort as list"
type: fix
status: completed
date: 2026-03-28
---

# fix: Forecast counter resolution uses same sort as list

When a user runs `bud ff` and sees forecast #3, then runs `bud forecast edit 3`, the edit command should target the same forecast. Currently, `list_forecasts` sorts named-first/unnamed-last, but `edit_forecast` and `delete_forecast` resolve counters using the unsorted DB order (`created_at`). This means counter #3 in the list may refer to a different forecast than counter #3 in edit/delete.

## Current State

| Command | Sort after fetching? |
|---------|---------------------|
| `forecast list` (`bud ff`) | Named-first sort (line 109) |
| `forecast edit` (counter) | No sort (line 357-358) |
| `forecast delete` (counter) | No sort (line 494-495) |
| `transaction create -f` (forecast counter) | No sort (line 138-143) |

**Transactions** and **recurrences** are already consistent — both use the same resolution path for list/edit/delete.

## Proposed Solution

Add the same named-first sort in the three places that resolve a forecast counter:

### 1. `forecast edit` — `bud/commands/forecasts.py:357-358`

```python
items = await forecast_service.list_forecasts(db, bid)
items = _filtered_forecasts(items, filter_expr)
# ADD: same sort as list_forecasts
if items:
    items.sort(key=lambda f: 0 if _forecast_description(f) else 1)
```

### 2. `forecast delete` — `bud/commands/forecasts.py:494-495`

```python
items = await forecast_service.list_forecasts(db, bid)
items = _filtered_forecasts(items, filter_expr)
# ADD: same sort as list_forecasts
if items:
    items.sort(key=lambda f: 0 if _forecast_description(f) else 1)
```

### 3. `transaction create -f` — `bud/commands/transactions.py:138`

```python
forecasts = await forecast_service.list_forecasts(db, budget_obj.id)
# ADD: same sort as list_forecasts
from bud.commands.forecasts import _forecast_description
forecasts.sort(key=lambda f: 0 if _forecast_description(f) else 1)
```

## Acceptance Criteria

- [ ] `forecast edit <N>` resolves the same forecast as shown at position #N in `bud ff`
- [ ] `forecast delete <N>` resolves the same forecast as shown at position #N in `bud ff`
- [ ] `transaction create -f <N>` resolves the same forecast as shown at position #N in `bud ff`
- [ ] All existing tests pass

## Files to Change

1. `bud/commands/forecasts.py` — add sort in `edit_forecast` and `delete_forecast`
2. `bud/commands/transactions.py` — add sort in `create_transaction` (forecast counter resolution)
