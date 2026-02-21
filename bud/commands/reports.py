import uuid
from datetime import date
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import require_user_id, resolve_project_id, resolve_budget_id, is_uuid
from bud.services import reports as report_service


@click.group()
def report():
    """Budget reports."""
    pass


@report.command("show")
@click.argument("budget_id", required=False, default=None)
@click.option("--project", "project_id", default=None, help="Project name or ID.")
@click.option("--transactions", "show_transactions", is_flag=True, default=False, help="Include all transactions in the report.")
def show_report(budget_id, project_id, show_transactions):
    """Show a budget report.

    BUDGET_ID can be a UUID or a budget name (YYYY-MM). If omitted, defaults
    to the current month's budget.
    """
    async def _run():
        user_id = require_user_id()
        async with get_session() as db:
            try:
                if budget_id is not None and is_uuid(budget_id):
                    bid = uuid.UUID(budget_id)
                else:
                    pid = await resolve_project_id(db, project_id, user_id)
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

            # Budget name as H1
            click.echo(f"# {r.budget_name}")
            click.echo(f"\n_{r.start_date} - {r.end_date}_")

            # Summary table: balance, earnings, expenses
            summary_rows = [
                ["Balance", f"{r.total_balance:.2f}"],
                ["Earnings", f"{r.total_earnings:.2f}"],
                ["Expenses", f"{r.total_expenses:.2f}"],
            ]
            click.echo()
            click.echo(tabulate(summary_rows, headers=["", "Amount"], tablefmt="github"))

            if r.account_balances:
                click.echo("\n## Account Balances\n")
                rows = [[b.account_name, f"{b.balance:.2f}"] for b in r.account_balances]
                click.echo(tabulate(rows, headers=["Account", "Balance"], tablefmt="github"))

            if r.forecasts:
                click.echo("\n## Forecasts vs Actuals\n")
                rows = [
                    [f.description, f"{f.forecast_value:.2f}", f"{f.actual_value:.2f}", f"{f.difference:.2f}"]
                    for f in r.forecasts
                ]
                click.echo(tabulate(rows, headers=["Description", "Forecast", "Actual", "Difference"], tablefmt="github"))

            if show_transactions:
                click.echo("\n## Transactions\n")
                if r.transactions:
                    rows = [
                        [str(t.date), t.description, f"{t.value:.2f}", t.source_account, t.destination_account]
                        for t in r.transactions
                    ]
                    click.echo(tabulate(rows, headers=["Date", "Description", "Amount", "From", "To"], tablefmt="github"))
                else:
                    click.echo("_No transactions found._")

    run_async(_run())
