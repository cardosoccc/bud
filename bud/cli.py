import click

from bud.commands.projects import project
from bud.commands.accounts import account
from bud.commands.categories import category
from bud.commands.transactions import transaction
from bud.commands.budgets import budget
from bud.commands.forecasts import forecast
from bud.commands.reports import report
from bud.commands.credentials import configure_aws, configure_gcp
from bud.commands.db_commands import db
from bud.commands.config_store import set_config_value


@click.group()
def cli():
    """bud - Budget management CLI."""
    pass


cli.add_command(project)
cli.add_command(account)
cli.add_command(category)
cli.add_command(transaction)
cli.add_command(budget)
cli.add_command(forecast)
cli.add_command(report)
cli.add_command(db)
cli.add_command(configure_aws)
cli.add_command(configure_gcp)

# Command group aliases
cli.add_command(transaction, name="txn")
cli.add_command(budget, name="bud")
cli.add_command(category, name="cat")
cli.add_command(forecast, name="for")
cli.add_command(project, name="prj")
cli.add_command(report, name="rep")
cli.add_command(account, name="acc")


@cli.command("set-month")
@click.argument("month")
def set_month(month):
    """Set the active month (YYYY-MM)."""
    set_config_value("active_month", month)
    click.echo(f"Active month set to: {month}")


@cli.command("set-config")
@click.argument("key")
@click.argument("value")
def set_config(key, value):
    """Set a configuration value (e.g. bucket s3://my-bucket)."""
    set_config_value(key, value)
    click.echo(f"{key}: {value}")


@cli.command("config")
@click.option("--show", is_flag=True, help="Show current config")
def config(show):
    """Show CLI configuration."""
    if show:
        from bud.commands.config_store import load_config
        cfg = load_config()
        for k, v in cfg.items():
            click.echo(f"{k}: {v}")


# Aliases for inline commands
cli.add_command(cli.commands["set-month"], name="mon")
cli.add_command(cli.commands["config"], name="cfg")


# List shortcuts: <alias>s lists the resource directly
@cli.command("txns")
@click.option("--month", default=None, help="YYYY-MM")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
@click.pass_context
def txns(ctx, month, project_id):
    """List transactions (alias for 'transaction list')."""
    ctx.invoke(transaction.commands["list"], month=month, project_id=project_id)


@cli.command("buds")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
@click.pass_context
def buds(ctx, project_id):
    """List budgets (alias for 'budget list')."""
    ctx.invoke(budget.commands["list"], project_id=project_id)


@cli.command("cats")
@click.pass_context
def cats(ctx):
    """List categories (alias for 'category list')."""
    ctx.invoke(category.commands["list"])


@cli.command("fors")
@click.option("--budget", "budget_id", required=True, help="Budget UUID or month name (YYYY-MM)")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
@click.pass_context
def fors(ctx, budget_id, project_id):
    """List forecasts (alias for 'forecast list')."""
    ctx.invoke(forecast.commands["list"], budget_id=budget_id, project_id=project_id)


@cli.command("prjs")
@click.pass_context
def prjs(ctx):
    """List projects (alias for 'project list')."""
    ctx.invoke(project.commands["list"])


@cli.command("accs")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
@click.pass_context
def accs(ctx, project_id):
    """List accounts (alias for 'account list')."""
    ctx.invoke(account.commands["list"], project_id=project_id)


if __name__ == "__main__":
    cli()
