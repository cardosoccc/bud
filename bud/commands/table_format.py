"""Table formatter with optional screen-width constraint.

By default tables are rendered at full (natural) width.  Pass
``screen=True`` to constrain output to MAX_WIDTH characters.

Column truncation priority (screen mode only):
  1. Numeric columns ("num") — never truncated, always fully visible
  2. Tag columns ("tag") — ellipsed first
  3. Text columns ("text") — use remaining space, ellipsed if needed
"""

from decimal import Decimal

MAX_WIDTH = 100


def format_table(headers, rows, col_types=None, screen=False):
    """Format *rows* under *headers*.

    Parameters
    ----------
    headers : list[str]
    rows : list[list]
        Raw values (int, float, Decimal, str, date, …).
    col_types : list[str] | None
        Per-column type hint — ``"num"``, ``"id"``, ``"tag"``, or ``"text"``
        (default).  ``"id"`` columns are never truncated but left-aligned.
    screen : bool
        When *True*, constrain the table to MAX_WIDTH characters (the
        previous default behaviour).  When *False* (default), columns use
        their natural width with no truncation.
    """
    n = len(headers)
    if col_types is None:
        col_types = ["text"] * n

    headers = [str(h) for h in headers]

    # --- stringify values ------------------------------------------------
    str_rows = []
    for row in rows:
        str_row = []
        for j, val in enumerate(row):
            str_row.append(_to_str(val, col_types[j]))
        str_rows.append(str_row)

    # --- compute natural content widths ----------------------------------
    natural = [len(h) for h in headers]
    for row in str_rows:
        for j, val in enumerate(row):
            natural[j] = max(natural[j], len(val))

    if screen:
        # Overhead per column: 2 chars padding (1 left + 1 right).
        # Between columns: 1 char for "|".
        # Total overhead = 2*n + (n-1) = 3n - 1
        overhead = 3 * n - 1
        available = MAX_WIDTH - overhead

        if sum(natural) <= available:
            widths = natural[:]
        else:
            widths = _compute_widths(headers, natural, col_types, available)
    else:
        widths = natural[:]

    # --- render ----------------------------------------------------------
    return _render(headers, str_rows, widths, col_types)


# ---- internal helpers ---------------------------------------------------

def _to_str(val, col_type):
    if val is None or val == "":
        return ""
    if col_type == "id":
        return str(val)
    if col_type == "num":
        if isinstance(val, (float, Decimal)):
            return f"{float(val):.2f}"
        if isinstance(val, int):
            return str(val)
        # Already a string (e.g. "yes", or pre-formatted)
        try:
            return f"{float(val):.2f}"
        except (ValueError, TypeError):
            return str(val)
    return str(val)


def _compute_widths(headers, natural, col_types, available):
    n = len(headers)
    widths = [0] * n

    # Fix numeric and id columns at natural width
    fixed = 0
    for j in range(n):
        if col_types[j] in ("num", "id"):
            widths[j] = natural[j]
            fixed += natural[j]

    remaining = available - fixed

    tag_indices = [j for j in range(n) if col_types[j] == "tag"]
    text_indices = [j for j in range(n) if col_types[j] == "text"]
    flex_indices = tag_indices + text_indices

    if not flex_indices:
        return widths

    flex_natural = sum(natural[j] for j in flex_indices)

    if flex_natural <= remaining:
        for j in flex_indices:
            widths[j] = natural[j]
        return widths

    # Need to shrink.  Tags shrink first, text gets the rest.
    tag_min = {j: max(len(headers[j]), 4) for j in tag_indices}
    tag_min_total = sum(tag_min.values())

    text_remaining = remaining - tag_min_total

    text_natural = sum(natural[j] for j in text_indices)

    if text_natural <= text_remaining:
        # Text fits naturally — give tags whatever extra is left.
        for j in text_indices:
            widths[j] = natural[j]
        tag_extra = text_remaining - text_natural
        if tag_indices:
            tag_natural_total = sum(natural[k] for k in tag_indices)
            for j in tag_indices:
                share = tag_min[j] + int(tag_extra * natural[j] / max(tag_natural_total, 1))
                widths[j] = min(share, natural[j])
    else:
        # Both tags and text need truncation.
        for j in tag_indices:
            widths[j] = tag_min[j]
        if text_indices:
            for j in text_indices:
                share = int(text_remaining * natural[j] / max(text_natural, 1))
                widths[j] = max(share, len(headers[j]), 4)

    # Fix rounding so total == available
    current = sum(widths)
    diff = available - current
    if diff != 0 and text_indices:
        widths[text_indices[0]] += diff
    elif diff != 0 and tag_indices:
        widths[tag_indices[0]] += diff

    # Ensure no width is below its header length (floor)
    for j in flex_indices:
        widths[j] = max(widths[j], min(len(headers[j]), 4))

    return widths


def _render(headers, str_rows, widths, col_types):
    def _cell(val, width, col_type):
        if col_type == "num":
            return f" {val:>{width}} "
        if len(val) > width:
            val = val[: width - 3] + "..." if width > 3 else val[:width]
        return f" {val:<{width}} "

    def _row(values):
        return "|".join(
            _cell(v, widths[j], col_types[j])
            for j, v in enumerate(values)
        )

    sep = "+".join("-" * (w + 2) for w in widths)
    lines = [_row(headers), sep]
    for row in str_rows:
        lines.append(_row(row))
    return "\n".join(lines)
