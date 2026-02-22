import uuid
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id, resolve_account_id, is_uuid
from bud.models.account import AccountType
from bud.schemas.account import AccountCreate, AccountUpdate
from bud.services import accounts as account_service


@click.group()
def account():
    """Manage accounts."""
    pass


@account.command("list")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
def list_accounts(project_id):
    """List accounts."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo("Error: no project specified. Use --project or set a default with `bud project set-default`.", err=True)
                return
            items = await account_service.list_accounts(db, pid)
            if not items:
                click.echo("No accounts found.")
                return
            rows = [[str(a.id), a.name, a.type.value] for a in items]
            click.echo(tabulate(rows, headers=["ID", "Name", "Type"], tablefmt="psql"))

    run_async(_run())


@account.command("create")
@click.option("--name", required=True)
@click.option("--type", "account_type", type=click.Choice(["credit", "debit", "nil"]), default="debit")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
def create_account(name, account_type, project_id):
    """Create a new account."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo("Error: no project specified. Use --project or set a default with `bud project set-default`.", err=True)
                return
            try:
                a = await account_service.create_account(
                    db, AccountCreate(name=name, type=AccountType(account_type), project_id=pid)
                )
                click.echo(f"Created account: {a.name} ({a.type.value}) id: {a.id}")
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)

    run_async(_run())


@account.command("edit")
@click.argument("account_id")
@click.option("--name", default=None)
@click.option("--type", "account_type", type=click.Choice(["credit", "debit", "nil"]), default=None)
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when ACCOUNT_ID is a name)")
def edit_account(account_id, name, account_type, project_id):
    """Edit an account. ACCOUNT_ID can be a UUID or account name."""
    async def _run():
        async with get_session() as db:
            if is_uuid(account_id):
                aid = uuid.UUID(account_id)
            else:
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("Error: --project required when using account name.", err=True)
                    return
                aid = await resolve_account_id(db, account_id, pid)
                if not aid:
                    click.echo(f"Account not found: {account_id}", err=True)
                    return
            atype = AccountType(account_type) if account_type else None
            a = await account_service.update_account(db, aid, AccountUpdate(name=name, type=atype))
            if not a:
                click.echo("Account not found.", err=True)
                return
            click.echo(f"Updated: {a.name} ({a.type.value})")

    run_async(_run())


@account.command("delete")
@click.argument("account_id")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when ACCOUNT_ID is a name)")
@click.confirmation_option(prompt="Delete this account?")
def delete_account(account_id, project_id):
    """Delete an account. ACCOUNT_ID can be a UUID or account name."""
    async def _run():
        async with get_session() as db:
            if is_uuid(account_id):
                aid = uuid.UUID(account_id)
            else:
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("Error: --project required when using account name.", err=True)
                    return
                aid = await resolve_account_id(db, account_id, pid)
                if not aid:
                    click.echo(f"Account not found: {account_id}", err=True)
                    return
            ok = await account_service.delete_account(db, aid)
            if not ok:
                click.echo("Account not found.", err=True)
                return
            click.echo("Account deleted.")

    run_async(_run())
