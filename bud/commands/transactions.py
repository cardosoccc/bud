import uuid
from datetime import date as date_type
import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import (
    resolve_project_id, resolve_account_id, resolve_category_id, is_uuid,
    require_month,
)
from bud.schemas.transaction import TransactionCreate, TransactionUpdate
from bud.services import transactions as transaction_service
from bud.services import forecasts as forecast_service
from bud.services import budgets as budget_service


@click.group()
def transaction():
    """Manage transactions."""
    pass


@transaction.command("list")
@click.argument("month", default=None, required=False)
@click.option("--project", "-p", "project_id", default=None, help="Project UUID or name")
@click.option("--show-id", "-s", is_flag=True, default=False, help="Show transaction UUIDs")
def list_transactions(month, project_id, show_id):
    """List transactions for a given month."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo("error: no project specified. use --project or set a default with `bud project set-default`.", err=True)
                return
            from bud.commands.utils import require_month
            m = require_month(month)
            items = await transaction_service.list_transactions(db, pid, m)
            if not items:
                click.echo("no transactions found.")
                return
            if show_id:
                rows = [
                    [i + 1, str(t.id), t.date, t.description, t.value, t.category.name if t.category else "", ", ".join(t.tags) if t.tags else "", t.account.name]
                    for i, t in enumerate(items)
                ]
                headers = ["#", "id", "date", "description", "value", "category", "tags", "account"]
            else:
                rows = [
                    [i + 1, t.date, t.description, t.value, t.category.name if t.category else "", ", ".join(t.tags) if t.tags else "", t.account.name]
                    for i, t in enumerate(items)
                ]
                headers = ["#", "date", "description", "value", "category", "tags", "account"]
            click.echo(tabulate(rows, headers=headers, tablefmt="presto", floatfmt=".2f"))

    run_async(_run())


@transaction.command("show")
@click.argument("transaction_id")
def show_transaction(transaction_id):
    """Show transaction details."""
    async def _run():
        async with get_session() as db:
            t = await transaction_service.get_transaction(db, uuid.UUID(transaction_id))
            if not t:
                click.echo("transaction not found.", err=True)
                return
            click.echo(f"id:          {t.id}")
            click.echo(f"date:        {t.date}")
            click.echo(f"description: {t.description}")
            click.echo(f"value:       {t.value}")
            click.echo(f"account:     {t.account.name}")
            click.echo(f"category:    {t.category_id or '-'}")
            click.echo(f"tags:        {', '.join(t.tags) if t.tags else '-'}")

    run_async(_run())


@transaction.command("create")
@click.option("--value", "-v", type=float, default=None, help="Amount (positive = income, negative = expense)")
@click.option("--description", "-d", default=None)
@click.option("--date", "-t", "txn_date", default=None, help="YYYY-MM-DD (default: today)")
@click.option("--account", "-a", "account_id", required=True, help="Account UUID or name")
@click.option("--project", "-p", "project_id", default=None, help="Project UUID or name")
@click.option("--category", "-c", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", default=None, help="Comma-separated tags")
@click.option("--forecast", "-f", "forecast_counter", type=int, default=None, help="Forecast # to create transaction from")
def create_transaction(value, description, txn_date, account_id, project_id, category_id, tags, forecast_counter):
    """Create a new transaction. Use positive values for income and negative for expenses.

    Use -f to create from a forecast: fields are pre-filled from the forecast and
    can be overridden with explicit options.
    """
    async def _run():
        d = date_type.fromisoformat(txn_date) if txn_date else date_type.today()
        tag_list = [t.strip() for t in tags.split(",")] if tags else None

        txn_value = value
        txn_desc = description
        txn_cat_id = category_id

        # When not using --forecast, value and description are required
        if forecast_counter is None:
            if txn_value is None:
                raise click.UsageError("--value is required (or use --forecast).")
            if txn_desc is None:
                raise click.UsageError("--description is required (or use --forecast).")

        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo("error: no project specified. use --project or set a default with `bud project set-default`.", err=True)
                return

            # When --forecast is provided, look up the forecast and pre-fill fields
            if forecast_counter is not None:
                month = f"{d.year}-{d.month:02d}"
                budget_obj = await budget_service.get_budget_by_name(db, pid, month)
                if not budget_obj:
                    click.echo(f"budget not found for month: {month}", err=True)
                    return
                forecasts = await forecast_service.list_forecasts(db, budget_obj.id)
                if forecast_counter < 1 or forecast_counter > len(forecasts):
                    click.echo(f"forecast #{forecast_counter} not found in list.", err=True)
                    return
                fc = forecasts[forecast_counter - 1]
                if txn_value is None:
                    txn_value = float(fc.value)
                if txn_desc is None:
                    desc = (fc.recurrence.base_description if fc.recurrence and fc.recurrence.base_description else fc.description) or ""
                    if fc.installment is not None and fc.recurrence and fc.recurrence.installments:
                        desc = f"{desc} ({fc.installment}/{fc.recurrence.installments})".strip()
                    txn_desc = desc
                if txn_cat_id is None and fc.category_id is not None:
                    txn_cat_id = str(fc.category_id)
                if tag_list is None and fc.tags:
                    tag_list = list(fc.tags)
            if tag_list is None:
                tag_list = []

            acc = await resolve_account_id(db, account_id, pid)
            if not acc:
                click.echo(f"account not found: {account_id}", err=True)
                return

            cat = None
            if txn_cat_id:
                cat = await resolve_category_id(db, txn_cat_id)
                if not cat:
                    if is_uuid(txn_cat_id):
                        click.echo(f"category not found: {txn_cat_id}", err=True)
                        return
                    if click.confirm(f"category '{txn_cat_id}' not found. create it?", default=False):
                        from bud.schemas.category import CategoryCreate
                        from bud.services import categories as category_service
                        new_cat = await category_service.create_category(db, CategoryCreate(name=txn_cat_id))
                        cat = new_cat.id
                        click.echo(f"created category: {new_cat.name}")
                    else:
                        return

            t = await transaction_service.create_transaction(db, TransactionCreate(
                value=txn_value,
                description=txn_desc,
                date=d,
                account_id=acc,
                project_id=pid,
                category_id=cat,
                tags=tag_list,
            ))
            click.echo(f"created transaction: {t.description} ({t.value}) id: {t.id}")

    run_async(_run())


@transaction.command("edit")
@click.argument("counter", required=False, type=int, default=None)
@click.option("--id", "record_id", default=None, help="Transaction UUID")
@click.option("--value", "-v", type=float, default=None)
@click.option("--description", "-d", default=None)
@click.option("--date", "-t", "txn_date", default=None)
@click.option("--category", "-c", "category_id", default=None, help="Category UUID or name")
@click.option("--tags", default=None, help="Comma-separated tags")
@click.argument("month", default=None, required=False)
@click.option("--project", "-p", "project_id", default=None, help="Project UUID or name (required when using counter)")
def edit_transaction(counter, record_id, value, description, txn_date, category_id, tags, month, project_id):
    """Edit a transaction. Specify by list counter (default) or --id."""
    async def _run():
        async with get_session() as db:
            if record_id:
                tid = uuid.UUID(record_id)
            elif counter is not None:
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("error: --project required when using counter.", err=True)
                    return
                m = require_month(month)
                items = await transaction_service.list_transactions(db, pid, m)
                if counter < 1 or counter > len(items):
                    click.echo(f"transaction #{counter} not found in list.", err=True)
                    return
                tid = items[counter - 1].id
            else:
                click.echo("error: provide a counter or --id.", err=True)
                return

            d = date_type.fromisoformat(txn_date) if txn_date else None
            tag_list = [t.strip() for t in tags.split(",")] if tags else None

            cat = None
            if category_id:
                cat = await resolve_category_id(db, category_id)
                if not cat:
                    if is_uuid(category_id):
                        click.echo(f"category not found: {category_id}", err=True)
                        return
                    if click.confirm(f"category '{category_id}' not found. create it?", default=False):
                        from bud.schemas.category import CategoryCreate
                        from bud.services import categories as category_service
                        new_cat = await category_service.create_category(db, CategoryCreate(name=category_id))
                        cat = new_cat.id
                        click.echo(f"created category: {new_cat.name}")
                    else:
                        return

            t = await transaction_service.update_transaction(db, tid, TransactionUpdate(
                value=value,
                description=description,
                date=d,
                category_id=cat,
                tags=tag_list,
            ))
            if not t:
                click.echo("transaction not found.", err=True)
                return
            click.echo(f"updated transaction: {t.description}")

    run_async(_run())


@transaction.command("delete")
@click.argument("transaction_id")
@click.argument("month", default=None, required=False)
@click.option("--project", "-p", "project_id", default=None, help="Project UUID or name (required when TRANSACTION_ID is a counter)")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt")
def delete_transaction(transaction_id, month, project_id, yes):
    """Delete a transaction. TRANSACTION_ID can be a UUID or a list counter (#)."""
    async def _run():
        async with get_session() as db:
            if transaction_id.isdigit():
                from bud.commands.utils import require_month
                pid = await resolve_project_id(db, project_id)
                if not pid:
                    click.echo("error: no project specified. use --project or set a default with `bud project set-default`.", err=True)
                    return
                m = require_month(month)
                items = await transaction_service.list_transactions(db, pid, m)
                n = int(transaction_id)
                if n < 1 or n > len(items):
                    click.echo(f"transaction #{n} not found in list.", err=True)
                    return
                t = items[n - 1]
                tid = t.id
                prompt = f"delete transaction #{n} (id: {tid})?"
            else:
                tid = uuid.UUID(transaction_id)
                prompt = f"delete transaction id: {tid}?"

            if not yes:
                click.confirm(prompt, abort=True)

            ok = await transaction_service.delete_transaction(db, tid)
            if not ok:
                click.echo("transaction not found.", err=True)
                return
            click.echo("transaction deleted.")

    run_async(_run())
