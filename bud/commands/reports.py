import uuid
from datetime import date
from decimal import Decimal

import click

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id, resolve_budget_id, is_uuid
from bud.services import reports as report_service

from bud.commands.table_format import format_table, _to_str, _render

_T1_HEADERS = ["account", "calculated", "current", "diff"]
_T1_COL_TYPES = ["text", "num", "num", "num"]

_T2_HEADERS = ["description", "category", "tags", "forecast", "current", "diff"]
_T2_COL_TYPES = ["text", "text", "tag", "num", "num", "num"]


def _fmt_row(values, col_types):
    """Format a single row using the shared renderer (for totals / special rows)."""
    str_vals = [_to_str(v, ct) for v, ct in zip(values, col_types)]
    # Compute widths from just this row (caller will join with table output)
    widths = [max(len(s), 4) for s in str_vals]
    return _render([], [str_vals], widths, col_types).split("\n")[-1]


def _build_report_table(headers, rows, col_types, screen=False):
    """Build a report table and return (table_str, separator, col_types) for appending extra rows."""
    return format_table(headers, rows, col_types, screen=screen)


def _report_extra_row(values, col_types, ref_table):
    """Format an extra row (total, expected, etc.) matching the widths of a rendered table."""
    # Extract widths from the separator line of the reference table
    sep_line = ref_table.split("\n")[1]
    widths = [len(seg) - 2 for seg in sep_line.split("+")]
    str_vals = [_to_str(v, ct) for v, ct in zip(values, col_types)]

    def _cell(val, width, is_num):
        if is_num:
            return f" {val:>{width}} "
        if len(val) > width:
            val = val[: width - 3] + "..." if width > 3 else val[:width]
        return f" {val:<{width}} "

    return "|".join(
        _cell(v, widths[j], col_types[j] == "num")
        for j, v in enumerate(str_vals)
    )


def _report_separator(ref_table):
    """Extract the separator line from a rendered table."""
    return ref_table.split("\n")[1]


@click.command()
@click.argument("budget_id", required=False, default=None)
@click.option("--project", "-p", "project_id", default=None, help="project name or id.")
@click.option("--screen", "-s", is_flag=True, default=False, help="fit table to screen (100 chars)")
def report(budget_id, project_id, screen):
    """show a budget report.

    budget_id can be a uuid or a budget name (yyyy-mm). if omitted, defaults
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
                            "error: no project specified. use --project or set a default with"
                            " `bud project set-default`.",
                            err=True,
                        )
                        return
                    identifier = budget_id if budget_id is not None else date.today().strftime("%Y-%m")
                    bid = await resolve_budget_id(db, identifier, pid)
                    if not bid:
                        click.echo(f"error: budget '{identifier}' not found.", err=True)
                        return
                r = await report_service.generate_report(db, bid)
            except ValueError as e:
                click.echo(f"error: {e}", err=True)
                return

            click.echo(f"\n# {r.budget_name} ({r.start_date} / {r.end_date})\n")
            click.echo("-" * 100)
            click.echo("## balances")
            click.echo("-" * 100)
            total_remaining = sum(f.difference for f in r.forecasts) if r.forecasts else Decimal("0")

            if r.account_balances:
                rows = [[b.account_name, b.calculated_balance, b.current_balance, b.difference] for b in r.account_balances]
                total_calc = sum(b.calculated_balance for b in r.account_balances)
                total_curr = sum(b.current_balance for b in r.account_balances)
                total_diff = sum(b.difference for b in r.account_balances)

                table = _build_report_table(_T1_HEADERS, rows, _T1_COL_TYPES, screen=screen)
                sep = _report_separator(table)
                total_row = _report_extra_row(["total", total_calc, total_curr, total_diff], _T1_COL_TYPES, table)
                acc_remaining = r.accumulated_remaining if r.accumulated_remaining is not None else total_remaining
                exp_calc = total_calc + acc_remaining
                exp_curr = total_curr + acc_remaining
                expected_row = _report_extra_row(["expected", exp_calc, exp_curr, total_diff], _T1_COL_TYPES, table)
                click.echo(f"{table}\n{sep}\n{total_row}\n{sep}\n{expected_row}")

            if r.forecasts or (r.is_projected and r.accumulated_remaining is not None):
                def _display_desc(f):
                    desc = f.description or ""
                    if f.installment is not None and f.total_installments is not None:
                        desc = f"{desc} ({f.installment}/{f.total_installments})".strip()
                    return desc

                sorted_forecasts = sorted(r.forecasts, key=lambda f: 0 if f.description else 1)

                rows = [
                    [_display_desc(f), f.category_name or "", ", ".join(f.tags) if f.tags else "", f.forecast_value, f.actual_value, f.difference]
                    for f in sorted_forecasts
                ]
                total_forecasted = sum(f.forecast_value for f in r.forecasts)
                total_current = sum(f.actual_value for f in r.forecasts)

                table = _build_report_table(_T2_HEADERS, rows, _T2_COL_TYPES, screen=screen)
                sep = _report_separator(table)
                total_row = _report_extra_row(["total", "", "", total_forecasted, total_current, total_remaining], _T2_COL_TYPES, table)
                click.echo("\n")
                click.echo("-" * 100)
                click.echo("## forecasts")
                click.echo("-" * 100)
                output = f"{table}\n{sep}\n{total_row}"

                is_future = r.start_date > date.today()
                if is_future and r.accumulated_remaining is not None:
                    prev_remaining = r.accumulated_remaining - total_remaining
                    prev_row = _report_extra_row(["previous", "", "", "", "", prev_remaining], _T2_COL_TYPES, table)
                    acc_row = _report_extra_row(["accumulated", "", "", "", "", r.accumulated_remaining], _T2_COL_TYPES, table)
                    output += f"\n{sep}\n{prev_row}\n{sep}\n{acc_row}"

                click.echo(output)

    run_async(_run())
