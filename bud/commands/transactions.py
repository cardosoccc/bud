import uuid
from datetime import date as date_type
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import require_user_id, require_project_id, require_month
from bud.schemas.transaction import TransactionCreate, TransactionUpdate
from bud.services import transactions as transaction_service


@click.group()
def transaction():
    """Manage transactions."""
    pass


@transaction.command("list")
@click.option("--month", default=None, help="YYYY-MM")
@click.option("--project", "project_id", default=None)
def list_transactions(month, project_id):
    """List transactions for a given month."""
    async def _run():
        user_id = require_user_id()
        pid = require_project_id(project_id)
        m = require_month(month)
        async with get_session() as db:
            items = await transaction_service.list_transactions(db, user_id, pid, m)
            if not items:
                click.echo("No transactions found.")
                return
            rows = [
                [str(t.id)[:8], t.date, t.description, str(t.value), str(t.source_account_id)[:8], str(t.destination_account_id)[:8]]
                for t in items
            ]
            click.echo(tabulate(rows, headers=["ID", "Date", "Description", "Value", "From", "To"]))

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
            click.echo(f"From:        {t.source_account_id}")
            click.echo(f"To:          {t.destination_account_id}")
            click.echo(f"Category:    {t.category_id or '-'}")
            click.echo(f"Tags:        {', '.join(t.tags) if t.tags else '-'}")

    run_async(_run())


@transaction.command("create")
@click.option("--value", required=True, type=float)
@click.option("--description", required=True)
@click.option("--date", "txn_date", default=None, help="YYYY-MM-DD (default: today)")
@click.option("--from", "source_id", required=True, help="Source account ID")
@click.option("--to", "dest_id", required=True, help="Destination account ID")
@click.option("--project", "project_id", default=None)
@click.option("--category", "category_id", default=None)
@click.option("--tags", default=None, help="Comma-separated tags")
def create_transaction(value, description, txn_date, source_id, dest_id, project_id, category_id, tags):
    """Create a new transaction."""
    async def _run():
        user_id = require_user_id()
        pid = require_project_id(project_id)
        d = date_type.fromisoformat(txn_date) if txn_date else date_type.today()
        tag_list = [t.strip() for t in tags.split(",")] if tags else []

        async with get_session() as db:
            t = await transaction_service.create_transaction(db, TransactionCreate(
                value=value,
                description=description,
                date=d,
                source_account_id=uuid.UUID(source_id),
                destination_account_id=uuid.UUID(dest_id),
                project_id=pid,
                category_id=uuid.UUID(category_id) if category_id else None,
                tags=tag_list,
            ))
            click.echo(f"Created transaction: {t.description} ({t.value}) id: {t.id}")

    run_async(_run())


@transaction.command("edit")
@click.argument("transaction_id")
@click.option("--value", type=float, default=None)
@click.option("--description", default=None)
@click.option("--date", "txn_date", default=None)
@click.option("--category", "category_id", default=None)
@click.option("--tags", default=None, help="Comma-separated tags")
def edit_transaction(transaction_id, value, description, txn_date, category_id, tags):
    """Edit a transaction."""
    async def _run():
        async with get_session() as db:
            d = date_type.fromisoformat(txn_date) if txn_date else None
            tag_list = [t.strip() for t in tags.split(",")] if tags else None
            t = await transaction_service.update_transaction(db, uuid.UUID(transaction_id), TransactionUpdate(
                value=value,
                description=description,
                date=d,
                category_id=uuid.UUID(category_id) if category_id else None,
                tags=tag_list,
            ))
            if not t:
                click.echo("Transaction not found.", err=True)
                return
            click.echo(f"Updated transaction: {t.description}")

    run_async(_run())


@transaction.command("delete")
@click.argument("transaction_id")
@click.confirmation_option(prompt="Delete this transaction?")
def delete_transaction(transaction_id):
    """Delete a transaction."""
    async def _run():
        async with get_session() as db:
            ok = await transaction_service.delete_transaction(db, uuid.UUID(transaction_id))
            if not ok:
                click.echo("Transaction not found.", err=True)
                return
            click.echo("Transaction deleted.")

    run_async(_run())
