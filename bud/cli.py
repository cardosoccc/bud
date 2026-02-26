import copy

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


def _list_alias(list_cmd: click.Command, alias_for: str, resource: str) -> click.Command:
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
        help=f"List {resource}  (alias: {alias_for})",
    )


def _add_subcommand_aliases(group: click.Group, aliases: dict[str, str]) -> None:
    """Register short aliases for subcommands within a group.

    *aliases* maps alias -> canonical subcommand name, e.g. {"e": "edit"}.
    """
    for alias, name in aliases.items():
        if name in group.commands:
            hidden = copy.copy(group.commands[name])
            hidden.hidden = True
            group.add_command(hidden, name=alias)


def _add_hidden_alias(group: click.Group, cmd: click.Command, alias: str) -> None:
    """Register *cmd* under *alias* as a hidden command and append the alias
    note to *cmd*'s own help text so it appears in the canonical entry."""
    cmd.help = ((cmd.help or "").rstrip(". ") + f"  (alias: {alias})")
    hidden = copy.copy(cmd)
    hidden.hidden = True
    group.add_command(hidden, name=alias)


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


@cli.group("config")
def config():
    """Manage CLI configuration."""
    pass


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set a configuration value."""
    set_config_value(key, value)
    click.echo(f"{key}: {value}")


@config.command("list")
def config_list():
    """List current configurations."""
    from bud.commands.config_store import load_config
    cfg = load_config()
    for k, v in cfg.items():
        click.echo(f"{k}: {v}")


config.add_command(configure_aws)
config.add_command(configure_gcp)


# Subcommand aliases (e=edit, c=create, d=delete, l=list, s=set)
_crud_aliases = {"e": "edit", "c": "create", "d": "delete", "l": "list"}
for _grp in (account, budget, category, transaction, project, forecast):
    _add_subcommand_aliases(_grp, _crud_aliases)
_add_subcommand_aliases(project, {"s": "set-default"})
_add_subcommand_aliases(config, {"s": "set"})

# Command group aliases — hidden so --help stays clean; the canonical command
# shows the alias in its own help line.
_add_hidden_alias(cli, transaction, "txn")
_add_hidden_alias(cli, budget,      "bdg")
_add_hidden_alias(cli, category,    "cat")
_add_hidden_alias(cli, forecast,    "fct")
_add_hidden_alias(cli, project,     "prj")
_add_hidden_alias(cli, report,      "rep")
_add_hidden_alias(cli, account,     "acc")

# Inline-command aliases
_add_hidden_alias(cli, cli.commands["config"],    "cfg")

# List shortcuts: delegate entirely to the underlying 'list' subcommand so that
# options added to 'list' are automatically available here too.
cli.add_command(_list_alias(transaction.commands["list"], "txn list", "transactions"), name="txns")
cli.add_command(_list_alias(account.commands["list"],     "acc list", "accounts"),     name="accs")
cli.add_command(_list_alias(budget.commands["list"],      "bud list", "budgets"),      name="bdgs")
cli.add_command(_list_alias(category.commands["list"],    "cat list", "categories"),   name="cats")
cli.add_command(_list_alias(forecast.commands["list"],    "for list", "forecasts"),    name="fcts")
cli.add_command(_list_alias(project.commands["list"],     "prj list", "projects"),     name="prjs")
cli.add_command(_list_alias(config.commands["list"],      "cfg list", "configs"),      name="cfgs")


if __name__ == "__main__":
    cli()
