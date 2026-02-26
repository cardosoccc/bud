import uuid
from datetime import date
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id, resolve_budget_id, is_uuid
from bud.services import reports as report_service


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

            click.echo(f"\n# {r.budget_name}  ({r.start_date} - {r.end_date})")
            summary = [
                ["Total Balance", r.total_balance],
                ["Total Earnings", r.total_earnings],
                ["Total Expenses", r.total_expenses],
            ]
            click.echo(f"\n{tabulate(summary, tablefmt="psql", floatfmt=".2f")}")

            if r.account_balances:
                rows = [[b.account_name, b.balance] for b in r.account_balances]
                click.echo(f"\n{tabulate(rows, headers=["Account", "Balance"], tablefmt="psql", floatfmt=".2f")}")

            if r.forecasts:
                rows = [
                    [f.description, f.forecast_value, f.actual_value, f.difference]
                    for f in r.forecasts
                ]
                click.echo(f"\n{tabulate(rows, headers=["Description", "Forecast", "Actual", "Difference"], tablefmt="psql", floatfmt=".2f")}")

    run_async(_run())
