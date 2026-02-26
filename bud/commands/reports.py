import uuid
from datetime import date
from decimal import Decimal

import click

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id, resolve_budget_id, is_uuid
from bud.services import reports as report_service

# Table 1: 4 cols, 5 separators → inner = 115
# | Account (43) | Calculated Balance (24) | Current Balance (24) | Difference (24) |
_T1_WIDTHS = [79, 12, 12, 12]
_T1_HEADERS = ["Account", "Calculated", "Current", "Difference"]
_T1_NUM = [False, True, True, True]

# Table 2: 6 cols, 7 separators → inner = 113
# | Description (40) | Category (12) | Tags (25) | Forecast (12) | Current (12) | Remaining (12) |
_T2_WIDTHS = [37, 15, 25, 12, 12, 12]
_T2_HEADERS = ["Description", "Category", "Tags", "Forecast", "Current", "Remaining"]
_T2_NUM = [False, False, False, True, True, True]


def _fmt_cell(val, width, numeric):
    inner = width - 2
    if numeric and val != "":
        s = f"{float(val):.2f}"
        return f" {s:>{inner}} "
    s = str(val)
    if len(s) > inner:
        s = s[: inner - 3] + "..."
    return f" {s:<{inner}} "


def _fmt_row(values, widths, numeric):
    return "|" + "|".join(_fmt_cell(v, w, n) for v, w, n in zip(values, widths, numeric)) + "|"


def _line(widths):
    '-' * widths

def _border(widths):
    return "+" + "+".join("-" * w for w in widths) + "+"


def _header_sep(widths):
    return "|" + "+".join("-" * w for w in widths) + "|"


def _build_table(headers, rows, widths, numeric):
    b = _border(widths)
    lines = [b, _fmt_row(headers, widths, [False] * len(widths)), _header_sep(widths)]
    for row in rows:
        lines.append(_fmt_row(row, widths, numeric))
    lines.append(b)
    return "\n".join(lines)


@click.command()
@click.argument("budget_id", required=False, default=None)
@click.option("--project", "project_id", default=None, help="Project name or ID.")
def report(budget_id, project_id):
    """Show a budget report.

    BUDGET_ID can be a UUID or a budget name (YYYY-MM). If omitted, defaults
    to the current month's budget.
    """
    async def _run():
        async with get_session() as db:
            try:
                if budget_id is not None and is_uuid(budget_id):
                    bid = uuid.UUID(budget_id)
                else:
                    pid = await resolve_project_id(db, project_id)
                    if not pid:
                        click.echo(
                            "Error: no project specified. Use --project or set a default with"
                            " `bud project set-default`.",
                            err=True,
                        )
                        return
                    identifier = budget_id if budget_id is not None else date.today().strftime("%Y-%m")
                    bid = await resolve_budget_id(db, identifier, pid)
                    if not bid:
                        click.echo(f"Error: budget '{identifier}' not found.", err=True)
                        return
                r = await report_service.generate_report(db, bid)
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)
                return

            click.echo(f"\n# {r.budget_name} ({r.start_date} / {r.end_date})")

            total_remaining = sum(f.difference for f in r.forecasts) if r.forecasts else Decimal("0")

            if r.account_balances:
                rows = [[b.account_name, b.calculated_balance, b.current_balance, b.difference] for b in r.account_balances]
                total_calc = sum(b.calculated_balance for b in r.account_balances)
                total_curr = sum(b.current_balance for b in r.account_balances)
                total_diff = sum(b.difference for b in r.account_balances)

                table = _build_table(_T1_HEADERS, rows, _T1_WIDTHS, _T1_NUM)
                b = _border(_T1_WIDTHS)
                total_row = _fmt_row(["Total", total_calc, total_curr, total_diff], _T1_WIDTHS, _T1_NUM)
                acc_remaining = r.accumulated_remaining if r.accumulated_remaining is not None else total_remaining
                exp_calc = total_calc + acc_remaining
                exp_curr = total_curr + acc_remaining
                expected_row = _fmt_row(["Expected", exp_calc, exp_curr, total_diff], _T1_WIDTHS, _T1_NUM)
                click.echo(f"\n{table}\n{total_row}\n{b}\n{expected_row}\n{b}")

            if r.forecasts or (r.is_projected and r.accumulated_remaining is not None):
                def _display_desc(f):
                    desc = f.description or ""
                    if f.installment is not None and f.total_installments is not None:
                        desc = f"{desc} ({f.installment}/{f.total_installments})".strip()
                    return desc

                rows = [
                    [_display_desc(f), f.category_name or "", ", ".join(f.tags) if f.tags else "", f.forecast_value, f.actual_value, f.difference]
                    for f in r.forecasts
                ]
                total_forecasted = sum(f.forecast_value for f in r.forecasts)
                total_current = sum(f.actual_value for f in r.forecasts)

                table = _build_table(_T2_HEADERS, rows, _T2_WIDTHS, _T2_NUM)
                b = _border(_T2_WIDTHS)
                total_row = _fmt_row(["Total", "", "", total_forecasted, total_current, total_remaining], _T2_WIDTHS, _T2_NUM)
                output = f"\n{table}\n{total_row}\n{b}"

                is_future = r.start_date > date.today()
                if is_future and r.accumulated_remaining is not None:
                    prev_remaining = r.accumulated_remaining - total_remaining
                    prev_row = _fmt_row(["Previous", "", "", "", "", prev_remaining], _T2_WIDTHS, _T2_NUM)
                    acc_row = _fmt_row(["Accumulated", "", "", "", "", r.accumulated_remaining], _T2_WIDTHS, _T2_NUM)
                    output += f"\n{prev_row}\n{b}\n{acc_row}\n{b}"

                click.echo(output)

    run_async(_run())
