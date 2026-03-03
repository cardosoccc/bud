"""Filter DSL for bud list/edit/delete commands.

Grammar (Option A — semicolon-separated):

    filter     := clause (";" clause)*
    clause     := field operator value
    field      := "c" | "t" | "v" | "d"
    operator   := "==" | ">=" | "<=" | "=" | ">" | "<"
    value      := <text>

Semantics:
    c  — category name, exact match (case-insensitive)
    t  — tags, comma-separated, AND logic (all must be present)
    d  — description: "=" substring (case-insensitive), "==" exact (case-insensitive)
    v  — value: numeric comparison

All clauses are combined with AND logic.

Examples:
    "c=outros;t=fixo,mercado;v>3;d=transfer"
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable, List, Optional


@dataclass
class FilterClause:
    field: str
    operator: str
    value: str


_CLAUSE_RE = re.compile(r"^([ctdv])(==|>=|<=|=|>|<)(.+)$")


def parse_filter(expr: str) -> List[FilterClause]:
    """Parse a semicolon-separated filter expression into clauses."""
    clauses: List[FilterClause] = []
    for part in expr.split(";"):
        part = part.strip()
        if not part:
            continue
        m = _CLAUSE_RE.match(part)
        if not m:
            raise ValueError(f"invalid filter clause: '{part}'")
        clauses.append(FilterClause(field=m.group(1), operator=m.group(2), value=m.group(3)))
    return clauses


def apply_filter(
    items: list,
    expr: str,
    get_category: Callable = lambda r: r.category.name if r.category else "",
    get_description: Callable = lambda r: r.description or "",
) -> list:
    """Filter items using a DSL expression. Returns the filtered list.

    get_category and get_description are callables that extract the
    category name and description from each record, allowing callers
    to customise for models that store these differently (e.g. forecasts
    use recurrence.base_description).
    """
    clauses = parse_filter(expr)
    return [item for item in items if _matches(item, clauses, get_category, get_description)]


def _matches(
    record,
    clauses: List[FilterClause],
    get_category: Callable,
    get_description: Callable,
) -> bool:
    for clause in clauses:
        if clause.field == "t":
            required = [t.strip() for t in clause.value.split(",")]
            tags = record.tags or []
            if not all(tag in tags for tag in required):
                return False

        elif clause.field == "c":
            cat = get_category(record)
            if cat.lower() != clause.value.lower():
                return False

        elif clause.field == "d":
            desc = get_description(record)
            if clause.operator == "==":
                if desc.lower() != clause.value.lower():
                    return False
            else:
                if clause.value.lower() not in desc.lower():
                    return False

        elif clause.field == "v":
            try:
                threshold = Decimal(clause.value)
            except InvalidOperation:
                raise ValueError(f"invalid numeric value in filter: '{clause.value}'")
            val = Decimal(str(record.value))
            if clause.operator in ("=", "=="):
                if val != threshold:
                    return False
            elif clause.operator == ">":
                if not (val > threshold):
                    return False
            elif clause.operator == "<":
                if not (val < threshold):
                    return False
            elif clause.operator == ">=":
                if not (val >= threshold):
                    return False
            elif clause.operator == "<=":
                if not (val <= threshold):
                    return False

    return True
