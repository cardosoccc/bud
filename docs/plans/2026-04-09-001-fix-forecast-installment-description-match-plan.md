---
title: "fix: Forecast matching uses bare description causing installment cross-match"
type: fix
status: completed
date: 2026-04-09
---

# fix: Forecast matching uses bare description causing installment cross-match

## Overview

When listing forecasts (`bud ff` / `bud s`), a moved installment forecast transaction
is incorrectly counted by a sibling installment forecast in the same budget, causing
the sibling to appear as partially or fully fulfilled when it should not be.

## Problem Statement

`compute_forecast_actual` (`bud/services/forecasts.py:83`) matches transactions with:

```python
if forecast.description and forecast.description.lower() not in t.description.lower():
    continue
```

For installment forecasts still linked to a recurrence, `forecast.description` stores
**only the bare base name** (e.g. `"autoglass"`). The display suffix `(N/total)` is
appended at render time in `commands/forecasts.py:119` and `commands/reports.py:117`,
but never fed back into the matching function.

**Scenario that triggers the bug:**

1. Month 2026-03 has installment-4 forecast, description = `"autoglass"`, installment = 4
2. That forecast is moved to month 2026-04 → it gets renamed to `"autoglass (4/9) (2026-03)"`,
   recurrence_id and installment are cleared
3. Month 2026-04 already has installment-5 forecast, description = `"autoglass"`, installment = 5
4. User stores a transaction with description `"autoglass (4/9) (2026-03)"`
5. `compute_forecast_actual` for the installment-5 forecast evaluates:
   `"autoglass"` in `"autoglass (4/9) (2026-03)"` → **True** → false match

Result: the installment-5 forecast is counted as fulfilled by the moved transaction,
even though no actual payment for installment 5 exists.

## Proposed Solution

Extract a helper `_effective_match_description(forecast)` that returns the
**effective display description** — including the `(N/total)` suffix for
recurrence-linked installment forecasts. Use this in `compute_forecast_actual`
instead of the raw `forecast.description`.

```python
# bud/services/forecasts.py

def _effective_match_description(forecast: Forecast) -> str | None:
    """Return the description string to use when matching transactions.

    For installment forecasts, includes the (N/total) suffix so that
    installment 5 of 9 only matches transactions containing "(5/9)",
    not transactions for other installment numbers.
    """
    if forecast.installment is not None and forecast.recurrence is not None:
        base = forecast.recurrence.base_description or forecast.description
        total = forecast.recurrence.installments
        suffix = f"{forecast.installment}/{total}" if total else str(forecast.installment)
        return f"{base} ({suffix})"
    return forecast.description


def compute_forecast_actual(forecast: Forecast, transactions: list) -> Decimal:
    ...
    match_desc = _effective_match_description(forecast)
    for t in transactions:
        ...
        if match_desc and match_desc.lower() not in t.description.lower():
            continue
        ...
```

### Secondary fix: eager-load recurrence in `_calculate_accumulated_remaining`

`_calculate_accumulated_remaining` (`bud/services/reports.py:178`) fetches forecasts
**without** `selectinload(Forecast.recurrence)`. After the fix, `compute_forecast_actual`
will access `forecast.recurrence`, which would raise a `MissingGreenlet` error in async
SQLAlchemy on a closed session. Add the missing option:

```python
# bud/services/reports.py:178
forecasts_result = await db.execute(
    select(Forecast)
    .where(Forecast.budget_id == b.id)
    .options(selectinload(Forecast.recurrence))  # add this
)
```

## Technical Considerations

- **No interface change**: `compute_forecast_actual` signature is unchanged; the helper
  is internal.
- **Non-installment forecasts are unaffected**: `_effective_match_description` returns
  `forecast.description` unchanged when `forecast.installment is None`.
- **Detached (moved) forecasts are unaffected**: after a move, both `recurrence_id` and
  `installment` are cleared (`forecasts.py:168-169`), so the helper returns the raw
  stored description as before.
- **`recurrence.installments` nullable**: the helper handles `total is None` by
  falling back to `"(N)"` (no denominator), matching the display render logic.
- **All three call sites** that pass forecasts to `compute_forecast_actual` will work
  correctly after the secondary fix:
  - `commands/forecasts.py:131` — already loads recurrence via `selectinload`
  - `services/reports.py:96-101` — already loads recurrence via `selectinload`
  - `services/reports.py:178` — **fixed** by the secondary fix above

## System-Wide Impact

- **Interaction graph**: only `compute_forecast_actual` is changed; it is called from
  `bud ff` listing, `bud s` status report, and `--adjust` editing. All paths converge
  on the same function.
- **Error propagation**: the `MissingGreenlet` risk in `_calculate_accumulated_remaining`
  is a silent latent crash introduced by the fix itself — the secondary fix eliminates it.
- **State lifecycle risks**: no state is mutated; this is a read-only computation fix.
- **API surface parity**: `ForecastActual` schema and all CLI outputs are unchanged.

## Acceptance Criteria

- [ ] Installment-5 forecast does **not** match a transaction with description
  `"autoglass (4/9) (2026-03)"` (the cross-match bug is fixed)
- [ ] Installment-5 forecast **does** match a transaction with description containing
  `"autoglass (5/9)"`
- [ ] Installment forecast with `recurrence.installments = None` does not crash;
  match string becomes `"autoglass (5)"` (no total denominator)
- [ ] Non-installment recurrent forecast (e.g. rent, no installment number) continues
  to match by bare base description — no behavior change
- [ ] Non-recurrent forecast continues to match by its stored description — no change
- [ ] `bud s` projected section (`_calculate_accumulated_remaining`) does not raise
  an error when installment forecasts are present in the iterated budgets
- [ ] All existing forecast matching tests continue to pass

## Dependencies & Risks

- **Risk**: Users who currently enter transactions with only the bare description
  (e.g. `"autoglass"`) rely on the loose substring match to fulfill an installment
  forecast. After this fix, the installment forecast will require `"autoglass (5/9)"`
  as a substring. This is the intended behavior (matching the display label), but
  existing users with loose transaction descriptions will see actuals drop to 0.
  **Mitigation**: document the expected transaction description convention; this
  behavior was already inconsistent before (the description shown in `bud ff` never
  matched what the matching function used).

## Files to Change

| File | Change |
|------|--------|
| `bud/services/forecasts.py` | Add `_effective_match_description` helper; update `compute_forecast_actual` to use it |
| `bud/services/reports.py` | Add `selectinload(Forecast.recurrence)` to `_calculate_accumulated_remaining` query |
| `tests/test_forecasts_command.py` | Add test: installment-5 does not match moved installment-4 transaction |
| `tests/test_forecasts_command.py` | Add test: installment-5 matches `"autoglass (5/9)"` transaction |

## Sources & References

- Bug location: `bud/services/forecasts.py:83`
- Move logic (sets fully-qualified description): `bud/services/forecasts.py:163`
- Display description construction: `bud/commands/forecasts.py:119-120`
- Missing selectinload: `bud/services/reports.py:178`
- Existing match tests: `tests/test_forecasts_command.py:346-476`
