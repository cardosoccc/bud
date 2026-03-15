import uuid
import click
from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id, resolve_account_id, is_uuid, with_auto_push
from bud.models.account import AccountType
from bud.schemas.account import AccountCreate, AccountUpdate
from bud.services import accounts as account_service


@click.group()
def account():
    """manage accounts."""
    pass


@account.command("list")
@click.option("--project", "-p", "project_id", default=None, help="project uuid or name")
@click.option("--show-id", "-s", is_flag=True, default=False, help="show account uuids")
@click.option("--type", "-t", "show_type", is_flag=True, default=False, help="show account type column")
@click.option("--initial-balance", "-i", "show_initial_balance", is_flag=True, default=False, help="show initial balance column")
def list_accounts(project_id, show_id, show_type, show_initial_balance):
    """list accounts."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo("error: no project specified. use --project or set a default with `bud project set-default`.", err=True)
                return
            items = await account_service.list_accounts(db, pid)
            if not items:
                click.echo("no accounts found.")
                return
            items = sorted(items, key=lambda a: a.name.lower())
            from bud.commands.table_format import format_table
            headers = ["#"]
            col_types = ["num"]
            if show_id:
                headers.append("id")
                col_types.append("id")
            headers.append("name")
            col_types.append("text")
            if show_type:
                headers.append("type")
                col_types.append("text")
            if show_initial_balance:
                headers.append("initial balance")
                col_types.append("num")
            headers.append("current balance")
            col_types.append("num")
            rows = []
            for i, a in enumerate(items):
                row = [i + 1]
                if show_id:
                    row.append(str(a.id))
                row.append(a.name)
                if show_type:
                    row.append(a.type.value)
                if show_initial_balance:
                    row.append(float(a.initial_balance))
                row.append(float(a.current_balance))
                rows.append(row)
            click.echo(format_table(headers, rows, col_types))

    run_async(_run())


@account.command("create")
@click.argument("name")
@click.option("--type", "-t", "account_type", type=click.Choice(["credit", "debit"]), default="debit")
@click.option("--project", "-p", "project_id", default=None, help="project uuid or name")
@click.option("--initial-balance", "-i", "initial_balance", type=float, default=0, help="initial balance (default: 0)")
@with_auto_push
def create_account(name, account_type, project_id, initial_balance):
    """create a new account."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo("error: no project specified. use --project or set a default with `bud project set-default`.", err=True)
                return
            try:
                a = await account_service.create_account(
                    db, AccountCreate(name=name, type=AccountType(account_type), project_id=pid, initial_balance=initial_balance)
                )
                click.echo(f"created account: {a.name} ({a.type.value}) id: {a.id}")
            except ValueError as e:
                click.echo(f"error: {e}", err=True)

    run_async(_run())


@account.command("edit")
@click.argument("identifier", required=False, default=None)
@click.option("--id", "record_id", default=None, help="account uuid")
@click.option("--name", "-n", default=None)
@click.option("--type", "-t", "account_type", type=click.Choice(["credit", "debit"]), default=None)
@click.option("--initial-balance", "-i", "initial_balance", type=float, default=None, help="set initial balance")
@click.option("--current-balance", "-c", "current_balance", type=float, default=None, help="set current balance")
@click.option("--project", "-p", "project_id", default=None, help="project uuid or name")
@with_auto_push
def edit_account(identifier, record_id, name, account_type, initial_balance, current_balance, project_id):
    """edit an account. specify by list counter or name (default) or --id."""
    async def _run():
        async with get_session() as db:
            if record_id:
                aid = uuid.UUID(record_id)
            elif identifier is not None:
                if is_uuid(identifier):
                    aid = uuid.UUID(identifier)
                else:
                    pid = await resolve_project_id(db, project_id)
                    if not pid:
                        click.echo("error: --project required when using counter or name.", err=True)
                        return
                    if identifier.isdigit():
                        items = await account_service.list_accounts(db, pid)
                        items = sorted(items, key=lambda a: a.name.lower())
                        n = int(identifier)
                        if n < 1 or n > len(items):
                            click.echo(f"account #{n} not found in list.", err=True)
                            return
                        aid = items[n - 1].id
                    else:
                        aid = await resolve_account_id(db, identifier, pid)
                        if not aid:
                            click.echo(f"account not found: {identifier}", err=True)
                            return
            else:
                click.echo("error: provide a counter, name, or --id.", err=True)
                return
            atype = AccountType(account_type) if account_type else None
            a = await account_service.update_account(
                db, aid, AccountUpdate(name=name, type=atype, initial_balance=initial_balance, current_balance=current_balance)
            )
            if not a:
                click.echo("account not found.", err=True)
                return
            click.echo(f"updated: {a.name} ({a.type.value})")

    run_async(_run())


@account.command("delete")
@click.argument("account_id")
@click.option("--project", "-p", "project_id", default=None, help="project uuid or name (required when account_id is a name or counter)")
@click.option("--yes", "-y", is_flag=True, default=False, help="skip confirmation prompt")
@with_auto_push
def delete_account(account_id, project_id, yes):
    """delete an account. account_id can be a uuid, name, or list counter (#)."""
    async def _run():
        async with get_session() as db:
            if account_id.isdigit():
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("error: --project required when using account counter.", err=True)
                    return
                items = await account_service.list_accounts(db, pid)
                items = sorted(items, key=lambda a: a.name.lower())
                n = int(account_id)
                if n < 1 or n > len(items):
                    click.echo(f"account #{n} not found in list.", err=True)
                    return
                aid = items[n - 1].id
                prompt = f"delete account #{n} (id: {aid})?"
            elif is_uuid(account_id):
                aid = uuid.UUID(account_id)
                prompt = f"delete account id: {aid}?"
            else:
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("error: --project required when using account name.", err=True)
                    return
                aid = await resolve_account_id(db, account_id, pid)
                if not aid:
                    click.echo(f"account not found: {account_id}", err=True)
                    return
                prompt = f"delete account id: {aid}?"

            if not yes:
                click.confirm(prompt, abort=True)

            ok = await account_service.delete_account(db, aid)
            if not ok:
                click.echo("account not found.", err=True)
                return
            click.echo("account deleted.")

    run_async(_run())
