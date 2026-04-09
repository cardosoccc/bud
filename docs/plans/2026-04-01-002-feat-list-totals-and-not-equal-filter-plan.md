---
title: "feat: Show totals in list commands and add not-equal filter operator"
type: feat
status: active
date: 2026-04-01
---

# feat: Show totals in list commands and add not-equal filter operator

## Overview

Two related improvements to list commands:

1. **Totals row** below forecast and transaction listings, computed from filtered results
2. **Not-equal filter operator** (`<>`) for the filter DSL -- works across all fields

Note: `>` and `<` operators already exist for numeric values (`bud/filter.py:114-119`). Only `<>` is missing.

## Proposed Solution

### 1. Add `<>` operator to filter DSL

Update the regex in `bud/filter.py:37` to include `<>`:

```python
_CLAUSE_RE = re.compile(r"^([actdv])(==|<>|>=|<=|=|>|<)(.+)$")
```

Add matching logic in `_matches()` for each field type:
- **`a` (account)**: `a<>bb` -- exclude records where account name equals "bb"
- **`c` (category)**: `c<>food` -- exclude records where category equals "food"
- **`t` (tags)**: `t<>fixo` -- exclude records that have ALL the specified tags
- **`d` (description)**: `d<>spotify` -- exclude records where description contains "spotify"
- **`v` (value)**: `v<>100` -- exclude records where value equals 100

### 2. Show totals after list output

Add a totals line after the table in both `forecast list` and `transaction list`.

**Forecast list** (`bud/commands/forecasts.py:86-144`):
- Show: `total: forecast={sum} current={sum} diff={sum}`
- Sum the `forecast`, `current`, and `diff` columns from the filtered items

**Transaction list** (`bud/commands/transactions.py:33-65`):
- Show: `total: {sum}`
- Sum the `value` column from the filtered items

The totals are calculated from the already-filtered items, so filters apply to totals automatically.

## Acceptance Criteria

- [ ] `<>` operator works for all 5 fields (a, c, t, d, v)
- [ ] `bud ff` shows totals line below the table (forecast, current, diff sums)
- [ ] `bud tt` shows totals line below the table (value sum)
- [ ] Totals reflect filtered results when `-f` is used
- [ ] Tests for `<>` operator on all field types
- [ ] Tests for totals in forecast and transaction list output

## MVP

### 1. Filter: add `<>` to regex and matching logic

#### bud/filter.py

Update regex (line 37):
```python
_CLAUSE_RE = re.compile(r"^([actdv])(==|<>|>=|<=|=|>|<)(.+)$")
```

Add `<>` handling in `_matches()` for each field:

```python
# account (line 80-83)
if clause.field == "a":
    acct = get_account(record)
    if clause.operator == "<>":
        if acct.lower() == clause.value.lower():
            return False
    elif acct.lower() != clause.value.lower():
        return False

# category (line 91-93) - same pattern
# tags (line 85-89) - "<>" means exclude if ALL tags present
# description (line 96-103) - "<>" means exclude if substring found
# value (line 105-125) - add elif for "<>" with != comparison
```

### 2. Forecast list: add totals

#### bud/commands/forecasts.py

After `click.echo(format_table(...))` (line 142), add:

```python
from decimal import Decimal
total_forecast = sum(Decimal(str(f.value)) for f in items)
total_current = sum(_current_value(f) for f in items)
total_diff = total_forecast - total_current
click.echo(f"total: forecast={total_forecast:.2f} current={total_current:.2f} diff={total_diff:.2f}")
```

### 3. Transaction list: add totals

#### bud/commands/transactions.py

After `click.echo(format_table(...))` (line 63), add:

```python
from decimal import Decimal
total_value = sum(Decimal(str(t.value)) for t in items)
click.echo(f"total: {total_value:.2f}")
```

### 4. Tests

#### tests/test_filter.py

```python
# Test: v<>100 excludes exact value match
# Test: d<>spotify excludes description containing "spotify"
# Test: c<>food excludes category "food"
# Test: a<>checking excludes account "checking"
# Test: t<>fixo excludes records with tag "fixo"
```

#### tests/test_forecasts_command.py

```python
# Test: forecast list shows totals line
# Test: forecast list with filter shows filtered totals
```

#### tests/test_transactions_command.py

```python
# Test: transaction list shows totals line
# Test: transaction list with filter shows filtered totals
```

## Sources & References

- Filter DSL: `bud/filter.py:37` (regex), `bud/filter.py:72-127` (matching)
- Forecast list: `bud/commands/forecasts.py:86-144`
- Transaction list: `bud/commands/transactions.py:33-65`
- Filter tests: `tests/test_filter.py`
