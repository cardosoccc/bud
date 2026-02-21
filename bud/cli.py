import click

from bud.commands.auth import auth
from bud.commands.projects import project
from bud.commands.accounts import account
from bud.commands.categories import category
from bud.commands.transactions import transaction
from bud.commands.budgets import budget
from bud.commands.forecasts import forecast
from bud.commands.reports import report
from bud.commands.config_store import set_config_value


@click.group()
def cli():
    """bud - Budget management CLI."""
    pass


cli.add_command(auth)
cli.add_command(project)
cli.add_command(account)
cli.add_command(category)
cli.add_command(transaction)
cli.add_command(budget)
cli.add_command(forecast)
cli.add_command(report)


@cli.command("set-month")
@click.argument("month")
def set_month(month):
    """Set the active month (YYYY-MM)."""
    set_config_value("active_month", month)
    click.echo(f"Active month set to: {month}")


@cli.command("config")
@click.option("--show", is_flag=True, help="Show current config")
def config(show):
    """Show CLI configuration."""
    if show:
        from bud.commands.config_store import load_config
        cfg = load_config()
        for k, v in cfg.items():
            click.echo(f"{k}: {v}")


if __name__ == "__main__":
    cli()
