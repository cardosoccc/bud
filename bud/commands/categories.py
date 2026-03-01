import uuid

import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_category_id
from bud.schemas.category import CategoryCreate, CategoryUpdate
from bud.services import categories as category_service


@click.group()
def category():
    """Manage categories."""
    pass


@category.command("list")
@click.option("--show-id", "-s", is_flag=True, default=False, help="Show category UUIDs")
def list_categories(show_id):
    """List all categories."""
    async def _run():
        async with get_session() as db:
            items = await category_service.list_categories(db)
            if not items:
                click.echo("no categories found.")
                return
            if show_id:
                rows = [[i + 1, str(c.id), c.name] for i, c in enumerate(items)]
                headers = ["#", "id", "name"]
            else:
                rows = [[i + 1, c.name] for i, c in enumerate(items)]
                headers = ["#", "name"]
            click.echo(tabulate(rows, headers=headers, tablefmt="presto"))

    run_async(_run())


@category.command("create")
@click.argument("name")
def create_category(name):
    """Create a new category."""
    async def _run():
        async with get_session() as db:
            c = await category_service.create_category(db, CategoryCreate(name=name))
            click.echo(f"created category: {c.name} (id: {c.id})")

    run_async(_run())


@category.command("edit")
@click.argument("counter", required=False, type=int, default=None)
@click.option("--id", "record_id", default=None, help="Category UUID")
@click.option("--name", "-n", required=True)
def edit_category(counter, record_id, name):
    """Edit a category. Specify by list counter (default) or --id."""
    async def _run():
        async with get_session() as db:
            if record_id:
                cid = uuid.UUID(record_id)
            elif counter is not None:
                items = await category_service.list_categories(db)
                if counter < 1 or counter > len(items):
                    click.echo(f"category #{counter} not found in list.", err=True)
                    return
                cid = items[counter - 1].id
            else:
                click.echo("error: provide a counter or --id.", err=True)
                return
            c = await category_service.update_category(db, cid, CategoryUpdate(name=name))
            if not c:
                click.echo("category not found.", err=True)
                return
            click.echo(f"updated: {c.name}")

    run_async(_run())


@category.command("delete")
@click.argument("category_id")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt")
def delete_category(category_id, yes):
    """Delete a category. CATEGORY_ID can be a UUID, name, or list counter (#)."""
    async def _run():
        async with get_session() as db:
            if category_id.isdigit():
                items = await category_service.list_categories(db)
                n = int(category_id)
                if n < 1 or n > len(items):
                    click.echo(f"category #{n} not found in list.", err=True)
                    return
                cid = items[n - 1].id
                prompt = f"delete category #{n} (id: {cid})?"
            else:
                cid = await resolve_category_id(db, category_id)
                if not cid:
                    click.echo(f"category not found: {category_id}", err=True)
                    return
                prompt = f"delete category id: {cid}?"

            if not yes:
                click.confirm(prompt, abort=True)

            ok = await category_service.delete_category(db, cid)
            if not ok:
                click.echo("category not found.", err=True)
                return
            click.echo("category deleted.")

    run_async(_run())
