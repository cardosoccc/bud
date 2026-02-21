import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import require_user_id, resolve_category_id
from bud.schemas.category import CategoryCreate, CategoryUpdate
from bud.services import categories as category_service


@click.group()
def category():
    """Manage categories."""
    pass


@category.command("list")
def list_categories():
    """List all categories."""
    async def _run():
        user_id = require_user_id()
        async with get_session() as db:
            items = await category_service.list_categories(db, user_id)
            if not items:
                click.echo("No categories found.")
                return
            rows = [[str(c.id), c.name] for c in items]
            click.echo(tabulate(rows, headers=["ID", "Name"], tablefmt="postgres"))

    run_async(_run())


@category.command("create")
@click.option("--name", required=True)
def create_category(name):
    """Create a new category."""
    async def _run():
        user_id = require_user_id()
        async with get_session() as db:
            c = await category_service.create_category(db, CategoryCreate(name=name), user_id)
            click.echo(f"Created category: {c.name} (id: {c.id})")

    run_async(_run())


@category.command("edit")
@click.argument("category_id")
@click.option("--name", required=True)
def edit_category(category_id, name):
    """Edit a category. CATEGORY_ID can be a UUID or category name."""
    async def _run():
        user_id = require_user_id()
        async with get_session() as db:
            cid = await resolve_category_id(db, category_id, user_id)
            if not cid:
                click.echo(f"Category not found: {category_id}", err=True)
                return
            c = await category_service.update_category(db, cid, user_id, CategoryUpdate(name=name))
            if not c:
                click.echo("Category not found.", err=True)
                return
            click.echo(f"Updated: {c.name}")

    run_async(_run())


@category.command("delete")
@click.argument("category_id")
@click.confirmation_option(prompt="Delete this category?")
def delete_category(category_id):
    """Delete a category. CATEGORY_ID can be a UUID or category name."""
    async def _run():
        user_id = require_user_id()
        async with get_session() as db:
            cid = await resolve_category_id(db, category_id, user_id)
            if not cid:
                click.echo(f"Category not found: {category_id}", err=True)
                return
            ok = await category_service.delete_category(db, cid, user_id)
            if not ok:
                click.echo("Category not found.", err=True)
                return
            click.echo("Category deleted.")

    run_async(_run())
