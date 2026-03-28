---
title: "feat: Consistent column names and sorting across forecast commands"
type: feat
status: completed
date: 2026-03-28
---

# feat: Consistent column names and sorting across forecast commands

## Overview

Make `bud ff` (forecast list) consistent with `bud s` (status) and `bud rr` (recurrence list) in two ways: use the same named-first sort ordering, add a diff column, and standardize column names to `forecast`, `current`, and `diff` across both commands.

## Problem Statement

Currently there are inconsistencies across commands:

| Issue | `bud ff` | `bud s` balances | `bud s` forecasts |
|-------|----------|------------------|-------------------|
| **Forecast amount col** | `value` | n/a | `forecast` |
| **Difference col** | *(missing)* | `difference` | `remaining` |
| **Sort order** | `created_at` (insertion) | named first, unnamed last | named first, unnamed last |

Target state: all commands use `forecast`/`current`/`diff` naming, `bud ff` shows a `diff` column, and `bud ff` sorts named items first (matching `bud s` and `bud rr`).

## Proposed Solution

Four changes across two files:

### 1. `bud ff` — add sort (named first, unnamed last)

**File:** `bud/commands/forecasts.py` — `list_forecasts` function (~line 106-107)

After loading items and applying filters, sort them the same way `bud s` and `bud rr` do:

```python
items.sort(key=lambda f: 0 if _forecast_description(f) else 1)
```

This reuses the existing `_forecast_description()` helper (line 68) which already handles recurrence base descriptions.

### 2. `bud ff` — rename `value` → `forecast`, add `diff` column

**File:** `bud/commands/forecasts.py` — `list_forecasts` function (~lines 132-139)

- Rename header `"value"` → `"forecast"`
- Add `"diff"` column after `"current"` with value `f.value - _current_value(f)`
- Update both `show_id` and non-`show_id` branches

Headers become: `#`, `description`, `forecast`, `current`, `diff`, `category`, `tags`, `recurrence`

### 3. `bud s` forecasts — rename `remaining` → `diff`

**File:** `bud/commands/reports.py` — line 16

```python
# before
_T2_HEADERS = ["description", "category", "tags", "forecast", "current", "remaining"]
# after
_T2_HEADERS = ["description", "category", "tags", "forecast", "current", "diff"]
```

No data changes needed — the values are already `forecast_value - actual_value`.

### 4. `bud s` balances — rename `difference` → `diff`

**File:** `bud/commands/reports.py` — line 13

```python
# before
_T1_HEADERS = ["account", "calculated", "current", "difference"]
# after
_T1_HEADERS = ["account", "calculated", "current", "diff"]
```

No data changes needed.

## Acceptance Criteria

- [ ] `bud ff` sorts forecasts named-first, unnamed-last (same as `bud s` and `bud rr`)
- [ ] `bud ff` shows columns: `#`, `description`, `forecast`, `current`, `diff`, `category`, `tags`, `recurrence`
- [ ] `bud ff` diff = forecast value minus current (matched transactions sum)
- [ ] `bud s` forecasts section shows `diff` instead of `remaining`
- [ ] `bud s` balances section shows `diff` instead of `difference`
- [ ] All existing tests pass after changes
- [ ] Column naming is consistent: `forecast`, `current`, `diff` used everywhere

## Files to Change

1. `bud/commands/forecasts.py` — sort + rename `value` → `forecast` + add `diff` column
2. `bud/commands/reports.py` — rename headers only (lines 13 and 16)
3. Tests referencing old column names (if any)
