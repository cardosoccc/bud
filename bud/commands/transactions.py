import uuid
from datetime import date as date_type
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import (
    resolve_project_id, resolve_account_id, resolve_category_id, is_uuid
)
from bud.schemas.transaction import TransactionCreate, TransactionUpdate
from bud.services import transactions as transaction_service


@click.group()
def transaction():
    """Manage transactions."""
    pass


@transaction.command("list")
@click.option("--month", default=None, help="YYYY-MM")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
@click.option("--show-id", is_flag=True, default=False, help="Show transaction UUIDs")
def list_transactions(month, project_id, show_id):
    """List transactions for a given month."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo("Error: no project specified. Use --project or set a default with `bud project set-default`.", err=True)
                return
            from bud.commands.utils import require_month
            m = require_month(month)
            items = await transaction_service.list_transactions(db, pid, m)
            if not items:
                click.echo("No transactions found.")
                return
            if show_id:
                rows = [
                    [i + 1, str(t.id), t.date, t.description, t.value, t.account.name]
                    for i, t in enumerate(items)
                ]
                headers = ["#", "ID", "Date", "Description", "Value", "Account"]
            else:
                rows = [
                    [i + 1, t.date, t.description, t.value, t.account.name]
                    for i, t in enumerate(items)
                ]
                headers = ["#", "Date", "Description", "Value", "Account"]
            click.echo(tabulate(rows, headers=headers, tablefmt="psql", floatfmt=".2f"))

    run_async(_run())


@transaction.command("show")
@click.argument("transaction_id")
def show_transaction(transaction_id):
    """Show transaction details."""
    async def _run():
        async with get_session() as db:
            t = await transaction_service.get_transaction(db, uuid.UUID(transaction_id))
            if not t:
                click.echo("Transaction not found.", err=True)
                return
            click.echo(f"ID:          {t.id}")
            click.echo(f"Date:        {t.date}")
            click.echo(f"Description: {t.description}")
            click.echo(f"Value:       {t.value}")
            click.echo(f"Account:     {t.account.name}")
            click.echo(f"Category:    {t.category_id or '-'}")
            click.echo(f"Tags:        {', '.join(t.tags) if t.tags else '-'}")

    run_async(_run())


@transaction.command("create")
@click.option("--value", required=True, type=float, help="Amount (positive = income, negative = expense)")
@click.option("--description", required=True)
@click.option("--date", "txn_date", default=None, help="YYYY-MM-DD (default: today)")
@click.option("--account", "account_id", required=True, help="Account UUID or name")
@click.option("--project", "project_id", default=None, help="Project UUID or name")
@click.option("--category", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", default=None, help="Comma-separated tags")
def create_transaction(value, description, txn_date, account_id, project_id, category_id, tags):
    """Create a new transaction. Use positive values for income and negative for expenses."""
    async def _run():
        d = date_type.fromisoformat(txn_date) if txn_date else date_type.today()
        tag_list = [t.strip() for t in tags.split(",")] if tags else []

        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo("Error: no project specified. Use --project or set a default with `bud project set-default`.", err=True)
                return

            acc = await resolve_account_id(db, account_id, pid)
            if not acc:
                click.echo(f"Account not found: {account_id}", err=True)
                return

            cat = None
            if category_id:
                cat = await resolve_category_id(db, category_id)
                if not cat:
                    if is_uuid(category_id):
                        click.echo(f"Category not found: {category_id}", err=True)
                        return
                    if click.confirm(f"Category '{category_id}' not found. Create it?", default=False):
                        from bud.schemas.category import CategoryCreate
                        from bud.services import categories as category_service
                        new_cat = await category_service.create_category(db, CategoryCreate(name=category_id))
                        cat = new_cat.id
                        click.echo(f"Created category: {new_cat.name}")
                    else:
                        return

            t = await transaction_service.create_transaction(db, TransactionCreate(
                value=value,
                description=description,
                date=d,
                account_id=acc,
                project_id=pid,
                category_id=cat,
                tags=tag_list,
            ))
            click.echo(f"Created transaction: {t.description} ({t.value}) id: {t.id}")

    run_async(_run())


@transaction.command("edit")
@click.argument("transaction_id")
@click.option("--value", type=float, default=None)
@click.option("--description", default=None)
@click.option("--date", "txn_date", default=None)
@click.option("--category", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", default=None, help="Comma-separated tags")
def edit_transaction(transaction_id, value, description, txn_date, category_id, tags):
    """Edit a transaction."""
    async def _run():
        async with get_session() as db:
            d = date_type.fromisoformat(txn_date) if txn_date else None
            tag_list = [t.strip() for t in tags.split(",")] if tags else None

            cat = None
            if category_id:
                cat = await resolve_category_id(db, category_id)
                if not cat:
                    if is_uuid(category_id):
                        click.echo(f"Category not found: {category_id}", err=True)
                        return
                    if click.confirm(f"Category '{category_id}' not found. Create it?", default=False):
                        from bud.schemas.category import CategoryCreate
                        from bud.services import categories as category_service
                        new_cat = await category_service.create_category(db, CategoryCreate(name=category_id))
                        cat = new_cat.id
                        click.echo(f"Created category: {new_cat.name}")
                    else:
                        return

            t = await transaction_service.update_transaction(db, uuid.UUID(transaction_id), TransactionUpdate(
                value=value,
                description=description,
                date=d,
                category_id=cat,
                tags=tag_list,
            ))
            if not t:
                click.echo("Transaction not found.", err=True)
                return
            click.echo(f"Updated transaction: {t.description}")

    run_async(_run())


@transaction.command("delete")
@click.argument("transaction_id")
@click.option("--month", default=None, help="YYYY-MM (required when TRANSACTION_ID is a counter)")
@click.option("--project", "project_id", default=None, help="Project UUID or name (required when TRANSACTION_ID is a counter)")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt")
def delete_transaction(transaction_id, month, project_id, yes):
    """Delete a transaction. TRANSACTION_ID can be a UUID or a list counter (#)."""
    async def _run():
        async with get_session() as db:
            if transaction_id.isdigit():
                from bud.commands.utils import require_month
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("Error: no project specified. Use --project or set a default with `bud project set-default`.", err=True)
                    return
                m = require_month(month)
                items = await transaction_service.list_transactions(db, pid, m)
                n = int(transaction_id)
                if n < 1 or n > len(items):
                    click.echo(f"Transaction #{n} not found in list.", err=True)
                    return
                t = items[n - 1]
                tid = t.id
                prompt = f"Delete transaction #{n} (id: {tid})?"
            else:
                tid = uuid.UUID(transaction_id)
                prompt = f"Delete transaction id: {tid}?"

            if not yes:
                click.confirm(prompt, abort=True)

            ok = await transaction_service.delete_transaction(db, tid)
            if not ok:
                click.echo("Transaction not found.", err=True)
                return
            click.echo("Transaction deleted.")

    run_async(_run())
