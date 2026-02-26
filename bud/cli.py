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


def _list_alias(list_cmd: click.Command, alias_for: str) -> click.Command:
    """Return a standalone command that delegates to *list_cmd*.

    The new command inherits all params from *list_cmd* (so it stays in sync
    automatically) and notes the canonical name in its help text.
    """
    @click.pass_context
    def _callback(ctx, **kwargs):
        return ctx.invoke(list_cmd, **kwargs)

    return click.Command(
        name=None,
        callback=_callback,
        params=list(list_cmd.params),
        help=f"(alias: {alias_for})\n\n{list_cmd.help or ''}",
    )


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


# List shortcuts: delegate entirely to the underlying 'list' subcommand so that
# options added to 'list' are automatically available here too.
cli.add_command(_list_alias(transaction.commands["list"], "txn list"), name="txns")
cli.add_command(_list_alias(account.commands["list"],     "acc list"), name="accs")
cli.add_command(_list_alias(budget.commands["list"],      "bud list"), name="buds")
cli.add_command(_list_alias(category.commands["list"],    "cat list"), name="cats")
cli.add_command(_list_alias(forecast.commands["list"],    "for list"), name="fors")
cli.add_command(_list_alias(project.commands["list"],     "prj list"), name="prjs")


if __name__ == "__main__":
    cli()
