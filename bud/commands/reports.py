import uuid
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import require_user_id
from bud.services import reports as report_service


@click.group()
def report():
    """Budget reports."""
    pass


@report.command("show")
@click.argument("budget_id")
def show_report(budget_id):
    """Show a budget report."""
    async def _run():
        require_user_id()
        async with get_session() as db:
            try:
                r = await report_service.generate_report(db, uuid.UUID(budget_id))
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)
                return

            click.echo(f"\nBudget: {r.budget_name}  ({r.start_date} - {r.end_date})")
            click.echo(f"Total Balance:   {r.total_balance:>12.2f}")
            click.echo(f"Total Earnings:  {r.total_earnings:>12.2f}")
            click.echo(f"Total Expenses:  {r.total_expenses:>12.2f}")

            if r.account_balances:
                click.echo("\nAccount Balances:")
                rows = [[b.account_name, f"{b.balance:.2f}"] for b in r.account_balances]
                click.echo(tabulate(rows, headers=["Account", "Balance"]))

            if r.forecasts:
                click.echo("\nForecasts vs Actuals:")
                rows = [
                    [f.description, f"{f.forecast_value:.2f}", f"{f.actual_value:.2f}", f"{f.difference:.2f}"]
                    for f in r.forecasts
                ]
                click.echo(tabulate(rows, headers=["Description", "Forecast", "Actual", "Difference"]))

    run_async(_run())
