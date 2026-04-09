---
status: pending
priority: p3
issue_id: "004"
tags: [code-review, quality, duplication]
dependencies: []
---

# Installment suffix formula f"{N}/{total}" duplicated in three places

## Problem Statement

The installment suffix pattern `f"{installment}/{total}"` is expressed identically in three locations. A format change (e.g. `N of T` or `N-T`) requires three coordinated edits with no compile-time enforcement.

## Findings

- `bud/services/forecasts.py:77` — `_effective_match_description`
- `bud/services/forecasts.py:179` — `move_forecast`
- `bud/commands/forecasts.py:120` — `_display_description` in `list` command
- Flagged by: architecture-strategist, code-simplicity-reviewer

## Proposed Solutions

### Option A: Extract to a shared utility function
```python
# bud/utils/installment.py (or inline in a shared module)
def installment_suffix(installment: int, total: int | None) -> str:
    return f"{installment}/{total}" if total else str(installment)
```
All three sites call this function.  
**Effort:** Small  **Risk:** Low

### Option B: Method on Recurrence model
Add `recurrence.installment_label(n)` that returns the formatted suffix.  
**Effort:** Small  **Risk:** Low

## Acceptance Criteria
- [ ] Suffix formula exists in exactly one place
- [ ] All three call sites use the shared function
- [ ] All tests pass

## Work Log
- 2026-04-09: Identified during ce-review of PR #42
