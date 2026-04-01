---
title: "feat: Move forecasts and transactions between budgets/months"
type: feat
status: completed
date: 2026-04-01
---

# feat: Move forecasts and transactions between budgets/months

## Overview

Allow changing the budget/month associated with forecasts and transactions via `--budget` option on edit commands. When moving recurrent forecasts, the behavior differs by recurrence type: installment-based forecasts move as-is (keeping their installment number), while simple recurrent forecasts get the source month appended to their description to avoid collisions with the auto-populated forecast in the target month.

## Problem Statement / Motivation

Currently, forecasts are locked to their budget (`budget_id` FK) with no way to re-assign them. If a user realizes a forecast belongs in a different month, they must delete it and recreate it manually. For recurrent forecasts this is especially tedious since the recurrence machinery auto-populates forecasts. Transactions can already have their date changed via `--date`, but there's no month-level shortcut.

## Proposed Solution

Add a `--budget`/`-b` option to `forecast edit` and a `--month`/`-m` option to `transaction edit` that allow re-assigning items to a different budget/month.

### Forecast move behavior

| Forecast type | Behavior when moved to target budget |
|---|---|
| **Non-recurrent** | Update `budget_id` to target budget. No description change. |
| **Installment-based recurrent** | Update `budget_id`. Keep `installment` number and `recurrence_id`. Delete the auto-populated forecast in the target budget (if one exists for the same recurrence). |
| **Simple recurrent** | Detach from recurrence (`recurrence_id = NULL`). Set description to `"{base_description} ({source_month})"`. The auto-populated forecast in the target budget (if any) remains untouched. |

### Transaction move behavior

Add `--month`/`-m` option to `transaction edit`. Changes the transaction's `date` to the same day in the target month, clamping to the last valid day (e.g., March 31 -> Feb 28). The target budget does NOT need to exist since transactions associate with budgets implicitly via date range.

## Technical Considerations

### Description collision for simple recurrences

When a simple recurrent forecast like "spotify" is moved from 2026-04 to 2026-05, the target budget already has its own auto-populated "spotify" from the recurrence. The moved forecast is detached from the recurrence and renamed to "spotify (2026-04)". Both coexist in the target month:
- "spotify" -- the auto-populated one (still linked to recurrence)
- "spotify (2026-04)" -- the moved one (no longer recurrent)

This avoids breaking the recurrence chain while preserving the user's intent.

### Transaction matching impact

`compute_forecast_actual` (`bud/services/forecasts.py:66-87`) uses `forecast.description.lower() not in t.description.lower()` -- the forecast description must be a substring of the transaction description. Since the moved forecast is detached from the recurrence and has a suffixed description like "spotify (2026-04)", it will NOT match transactions named "spotify". This is acceptable because the moved forecast represents a shifted budget allocation, not a new matching rule. The original auto-populated "spotify" forecast in the target month still handles matching.

### Installment collision handling

When moving installment 3/10 from 2026-04 to 2026-05, the target budget may already have installment 4/10 from auto-population. The system deletes the auto-populated forecast for the same recurrence in the target budget before moving. This means the user explicitly takes control of the installment placement. The source month loses its forecast -- if the budget is later recreated, `_populate_recurrent_forecasts` will re-create the computed installment for that month.

### Auto-creation of target budget

When the target budget doesn't exist, auto-create it (matching the pattern in `_resolve_or_create_budget_id`). This triggers `_populate_recurrent_forecasts`, which is fine -- the move logic runs after budget creation and handles any collision.

## Acceptance Criteria

- [ ] `bud forecast edit <counter> --budget <month>` moves a non-recurrent forecast to the target budget
- [ ] Moving a simple recurrent forecast detaches it from recurrence and appends `({source_month})` to description
- [ ] Moving an installment-based forecast keeps installment number and replaces the auto-populated forecast in the target budget
- [ ] `bud transaction edit <counter> --month <month>` changes the transaction date to the same day in the target month
- [ ] Day is clamped to last valid day when target month is shorter (e.g., 31 -> 28)
- [ ] Target budget is auto-created if it doesn't exist
- [ ] Error if forecast is already in the target budget
- [ ] Tests cover all three forecast types and transaction month change

## MVP

### 1. Schema: add `budget_id` to `ForecastUpdate`

#### bud/schemas/forecast.py

```python
class ForecastUpdate(BaseModel):
    description: Optional[str] = None
    value: Optional[Decimal] = None
    category_id: Optional[uuid.UUID] = None
    tags: Optional[List[str]] = None
    budget_id: Optional[uuid.UUID] = None
```

### 2. Service: add `move_forecast` to forecast service

#### bud/services/forecasts.py

```python
async def move_forecast(
    db: AsyncSession,
    forecast_id: uuid.UUID,
    target_budget_id: uuid.UUID,
    source_budget_name: str,
) -> Forecast:
    """Move a forecast to a different budget, handling recurrence logic."""
    forecast = await get_forecast(db, forecast_id)
    if not forecast:
        return None
    if forecast.budget_id == target_budget_id:
        return None  # already in target

    if forecast.recurrence_id:
        if forecast.installment:
            # Installment-based: delete auto-populated forecast in target, move this one
            existing = await _get_forecast_for_recurrence_in_budget(
                db, forecast.recurrence_id, target_budget_id
            )
            if existing:
                await db.delete(existing)
            forecast.budget_id = target_budget_id
        else:
            # Simple recurrent: detach and rename
            rec = await db.execute(
                select(Recurrence).where(Recurrence.id == forecast.recurrence_id)
            )
            rec_obj = rec.scalar_one_or_none()
            base = rec_obj.base_description if rec_obj else forecast.description
            forecast.description = f"{base} ({source_budget_name})"
            forecast.recurrence_id = None
            forecast.budget_id = target_budget_id
    else:
        # Non-recurrent: simple move
        forecast.budget_id = target_budget_id

    await db.commit()
    await db.refresh(forecast)
    return forecast
```

Add a helper to find the existing forecast for a recurrence in a budget:

```python
async def _get_forecast_for_recurrence_in_budget(
    db: AsyncSession, recurrence_id: uuid.UUID, budget_id: uuid.UUID
) -> Optional[Forecast]:
    result = await db.execute(
        select(Forecast).where(
            Forecast.recurrence_id == recurrence_id,
            Forecast.budget_id == budget_id,
        )
    )
    return result.scalar_one_or_none()
```

### 3. CLI: add `--budget` option to `forecast edit`

#### bud/commands/forecasts.py

Add `--budget` / `-b` option to `edit_forecast`:

```python
@click.option("--budget", "-b", "target_budget", default=None,
              help="move forecast to this budget (month name or uuid)")
```

In the `_run()` body, after resolving `fid`, add the move branch:

```python
if target_budget:
    # Resolve target budget (auto-create if needed)
    target_bid = await _resolve_or_create_budget_id(db, target_budget, project_id)
    if not target_bid:
        return
    # Get source budget name for description suffix
    forecast_obj = await forecast_service.get_forecast(db, fid)
    source_budget = await budget_service.get_budget(db, forecast_obj.budget_id)
    result = await forecast_service.move_forecast(
        db, fid, target_bid, source_budget.name
    )
    if not result:
        click.echo("error: forecast not found or already in target budget.", err=True)
        return
    click.echo(f"moved forecast to {target_budget}: {result.description}")
    return
```

### 4. CLI: add `--month` option to `transaction edit`

#### bud/commands/transactions.py

Add `--month` / `-m` option to `edit_transaction`:

```python
@click.option("--month", "-m", "target_month", default=None,
              help="move transaction to this month (yyyy-mm)")
```

In the `_run()` body, compute new date when `target_month` is provided:

```python
if target_month:
    import calendar
    txn = await transaction_service.get_transaction(db, tid)
    if not txn:
        click.echo("transaction not found.", err=True)
        return
    year, month_num = map(int, target_month.split("-"))
    last_day = calendar.monthrange(year, month_num)[1]
    new_day = min(txn.date.day, last_day)
    d = date_type(year, month_num, new_day)
```

### 5. Tests

#### tests/test_forecast_move.py

```python
# Test: move non-recurrent forecast to another budget
# Test: move simple recurrent forecast detaches and renames
# Test: move installment forecast replaces auto-populated in target
# Test: move to same budget returns error
# Test: target budget auto-created when missing
```

#### tests/test_transaction_month.py

```python
# Test: move transaction to different month via --month
# Test: day clamped to last day of shorter month
```

## Success Metrics

- Users can reclassify forecasts between months without delete/recreate
- Recurrence integrity is preserved (no orphaned or duplicate recurrence forecasts)
- Transaction matching continues to work correctly for non-moved forecasts

## Dependencies & Risks

- **Risk:** Moving an installment forecast breaks the computed installment sequence. The auto-population logic uses `get_installment_number()` which derives installment number from month offset. If a user manually moves installments around, future budget creation may auto-populate a conflicting installment. Mitigation: the `forecast_exists_for_recurrence` check prevents duplicates; the moved forecast retains the manually-set installment number.
- **Risk:** Moving a simple recurrent forecast and then re-creating the source budget will auto-populate the original forecast again. This is expected behavior -- the recurrence still covers that month.

## Sources & References

- Forecast service: `bud/services/forecasts.py`
- Budget service (recurrence population): `bud/services/budgets.py:62-90`
- Recurrence service: `bud/services/recurrences.py`
- Forecast CLI edit command: `bud/commands/forecasts.py:318-465`
- Transaction CLI edit command: `bud/commands/transactions.py:196-260`
- ForecastUpdate schema: `bud/schemas/forecast.py:33-37`
