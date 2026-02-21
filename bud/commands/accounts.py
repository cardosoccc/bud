import uuid
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import require_user_id, require_project_id
from bud.models.account import AccountType
from bud.schemas.account import AccountCreate, AccountUpdate
from bud.services import accounts as account_service


@click.group()
def account():
    """Manage accounts."""
    pass


@account.command("list")
@click.option("--project", "project_id", default=None)
def list_accounts(project_id):
    """List accounts."""
    async def _run():
        user_id = require_user_id()
        pid = require_project_id(project_id)
        async with get_session() as db:
            items = await account_service.list_accounts(db, user_id, pid)
            if not items:
                click.echo("No accounts found.")
                return
            rows = [[str(a.id), a.name, a.type.value] for a in items]
            click.echo(tabulate(rows, headers=["ID", "Name", "Type"]))

    run_async(_run())


@account.command("create")
@click.option("--name", required=True)
@click.option("--type", "account_type", type=click.Choice(["credit", "debit", "nil"]), default="debit")
@click.option("--project", "project_id", default=None)
def create_account(name, account_type, project_id):
    """Create a new account."""
    async def _run():
        user_id = require_user_id()
        pid = require_project_id(project_id)
        async with get_session() as db:
            try:
                a = await account_service.create_account(
                    db, AccountCreate(name=name, type=AccountType(account_type), project_id=pid), user_id
                )
                click.echo(f"Created account: {a.name} ({a.type.value}) id: {a.id}")
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)

    run_async(_run())


@account.command("edit")
@click.argument("account_id")
@click.option("--name", default=None)
@click.option("--type", "account_type", type=click.Choice(["credit", "debit", "nil"]), default=None)
def edit_account(account_id, name, account_type):
    """Edit an account."""
    async def _run():
        async with get_session() as db:
            atype = AccountType(account_type) if account_type else None
            a = await account_service.update_account(db, uuid.UUID(account_id), AccountUpdate(name=name, type=atype))
            if not a:
                click.echo("Account not found.", err=True)
                return
            click.echo(f"Updated: {a.name} ({a.type.value})")

    run_async(_run())


@account.command("delete")
@click.argument("account_id")
@click.confirmation_option(prompt="Delete this account?")
def delete_account(account_id):
    """Delete an account."""
    async def _run():
        async with get_session() as db:
            ok = await account_service.delete_account(db, uuid.UUID(account_id))
            if not ok:
                click.echo("Account not found.", err=True)
                return
            click.echo("Account deleted.")

    run_async(_run())
