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
@click.option("--show-id", is_flag=True, default=False, help="Show account UUIDs")
def list_accounts(project_id, show_id):
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
            items = sorted(items, key=lambda a: a.name.lower())
            if show_id:
                rows = [[i + 1, str(a.id), a.name, a.type.value, float(a.initial_balance), float(a.current_balance)] for i, a in enumerate(items)]
                headers = ["#", "ID", "Name", "Type", "Initial Balance", "Current Balance"]
            else:
                rows = [[i + 1, a.name, a.type.value, float(a.initial_balance), float(a.current_balance)] for i, a in enumerate(items)]
                headers = ["#", "Name", "Type", "Initial Balance", "Current Balance"]
            click.echo(tabulate(rows, headers=headers, tablefmt="psql", floatfmt=".2f"))

    run_async(_run())


@account.command("create")
@click.argument("name")
@click.option("--type", "account_type", type=click.Choice(["credit", "debit"]), default="debit")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
@click.option("--initial-balance", "initial_balance", type=float, default=0, help="Initial balance (default: 0)")
def create_account(name, account_type, project_id, initial_balance):
    """Create a new account."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo("Error: no project specified. Use --project or set a default with `bud project set-default`.", err=True)
                return
            try:
                a = await account_service.create_account(
                    db, AccountCreate(name=name, type=AccountType(account_type), project_id=pid, initial_balance=initial_balance)
                )
                click.echo(f"Created account: {a.name} ({a.type.value}) id: {a.id}")
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)

    run_async(_run())


@account.command("edit")
@click.argument("identifier", required=False, default=None)
@click.option("--id", "record_id", default=None, help="Account UUID")
@click.option("--name", default=None)
@click.option("--type", "account_type", type=click.Choice(["credit", "debit"]), default=None)
@click.option("--initial-balance", "initial_balance", type=float, default=None, help="Set initial balance")
@click.option("--current-balance", "current_balance", type=float, default=None, help="Set current balance")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
def edit_account(identifier, record_id, name, account_type, initial_balance, current_balance, project_id):
    """Edit an account. Specify by list counter or name (default) or --id."""
    async def _run():
        async with get_session() as db:
            if record_id:
                aid = uuid.UUID(record_id)
            elif identifier is not None:
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("Error: --project required when using counter or name.", err=True)
                    return
                if identifier.isdigit():
                    items = await account_service.list_accounts(db, pid)
                    items = sorted(items, key=lambda a: a.name.lower())
                    n = int(identifier)
                    if n < 1 or n > len(items):
                        click.echo(f"Account #{n} not found in list.", err=True)
                        return
                    aid = items[n - 1].id
                else:
                    aid = await resolve_account_id(db, identifier, pid)
                    if not aid:
                        click.echo(f"Account not found: {identifier}", err=True)
                        return
            else:
                click.echo("Error: provide a counter, name, or --id.", err=True)
                return
            atype = AccountType(account_type) if account_type else None
            a = await account_service.update_account(
                db, aid, AccountUpdate(name=name, type=atype, initial_balance=initial_balance, current_balance=current_balance)
            )
            if not a:
                click.echo("Account not found.", err=True)
                return
            click.echo(f"Updated: {a.name} ({a.type.value})")

    run_async(_run())


@account.command("delete")
@click.argument("account_id")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when ACCOUNT_ID is a name or counter)")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt")
def delete_account(account_id, project_id, yes):
    """Delete an account. ACCOUNT_ID can be a UUID, name, or list counter (#)."""
    async def _run():
        async with get_session() as db:
            if account_id.isdigit():
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("Error: --project required when using account counter.", err=True)
                    return
                items = await account_service.list_accounts(db, pid)
                items = sorted(items, key=lambda a: a.name.lower())
                n = int(account_id)
                if n < 1 or n > len(items):
                    click.echo(f"Account #{n} not found in list.", err=True)
                    return
                aid = items[n - 1].id
                prompt = f"Delete account #{n} (id: {aid})?"
            elif is_uuid(account_id):
                aid = uuid.UUID(account_id)
                prompt = f"Delete account id: {aid}?"
            else:
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("Error: --project required when using account name.", err=True)
                    return
                aid = await resolve_account_id(db, account_id, pid)
                if not aid:
                    click.echo(f"Account not found: {account_id}", err=True)
                    return
                prompt = f"Delete account id: {aid}?"

            if not yes:
                click.confirm(prompt, abort=True)

            ok = await account_service.delete_account(db, aid)
            if not ok:
                click.echo("Account not found.", err=True)
                return
            click.echo("Account deleted.")

    run_async(_run())
