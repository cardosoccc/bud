import copy

import click

from bud.commands.projects import project
from bud.commands.accounts import account
from bud.commands.categories import category
from bud.commands.transactions import transaction
from bud.commands.budgets import budget
from bud.commands.forecasts import forecast
from bud.commands.reports import report
from bud.commands.recurrences import recurrence
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
        help=f"List {resource}  (alias for: {alias_for})",
    )


def _add_subcommand_aliases(group: click.Group, aliases: dict[str, str]) -> None:
    """Register short aliases for subcommands within a group.

    *aliases* maps alias -> canonical subcommand name, e.g. {"e": "edit"}.
    The alias becomes the visible command; the canonical name becomes hidden.
    """
    for alias, name in aliases.items():
        if name in group.commands:
            _add_visible_alias(group, group.commands[name], alias, name)


def _add_visible_alias(group: click.Group, cmd: click.Command, alias: str, canonical_name: str) -> None:
    """Register *alias* as a visible command and hide the canonical one.

    The alias shows '(alias for: <canonical_name>)' in its help text.
    The canonical command becomes hidden but still works.
    """
    # Make the canonical command hidden
    cmd.hidden = True

    # Create visible alias with "(alias for: ...)" in short_help
    visible = copy.copy(cmd)
    visible.hidden = False
    # Derive short help from the first line of the help text
    raw = cmd.short_help or (cmd.help or "").split("\n")[0]
    base_short = raw.split("(alias for:")[0].rstrip(". ")
    visible.short_help = f"{base_short}  (alias for: {canonical_name})"
    group.add_command(visible, name=alias)


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
cli.add_command(report, "status")
cli.add_command(recurrence)
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
_crud_aliases = {"e": "edit", "c": "create", "d": "delete", "l": "list", "s": "show"}
for _grp in (account, budget, category, transaction, project, forecast):
    _add_subcommand_aliases(_grp, _crud_aliases)
_add_subcommand_aliases(recurrence, {"l": "list", "e": "edit", "d": "delete"})
_add_subcommand_aliases(project, {"s": "set-default"})
_add_subcommand_aliases(config, {"s": "set"})

# Command group aliases — alias is visible, canonical name is hidden.
_add_visible_alias(cli, transaction, "t",  "transaction")
_add_visible_alias(cli, budget,      "b",  "budget")
_add_visible_alias(cli, category,    "c",  "category")
_add_visible_alias(cli, forecast,    "f",  "forecast")
_add_visible_alias(cli, project,     "p",  "project")
_add_visible_alias(cli, recurrence,  "r",  "recurrence")
_add_visible_alias(cli, account,     "a",  "account")
_add_visible_alias(cli, cli.commands["status"], "s", "status")

# Inline-command aliases
_add_visible_alias(cli, cli.commands["config"], "g", "config")

# List shortcuts: delegate entirely to the underlying 'list' subcommand so that
# options added to 'list' are automatically available here too.
cli.add_command(_list_alias(transaction.commands["list"], "t list", "transactions"), name="tt")
cli.add_command(_list_alias(account.commands["list"],     "a list", "accounts"),     name="aa")
cli.add_command(_list_alias(budget.commands["list"],      "b list", "budgets"),      name="bb")
cli.add_command(_list_alias(category.commands["list"],    "c list", "categories"),   name="cc")
cli.add_command(_list_alias(forecast.commands["list"],    "f list", "forecasts"),    name="ff")
cli.add_command(_list_alias(project.commands["list"],     "p list", "projects"),     name="pp")
cli.add_command(_list_alias(recurrence.commands["list"], "r list", "recurrences"), name="rr")
cli.add_command(_list_alias(config.commands["list"],      "g list", "configurations"), name="gg")


if __name__ == "__main__":
    cli()
