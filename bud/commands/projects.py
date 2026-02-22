import click
from tabulate import tabulate

from bud.commands.db import get_session, run_async
from bud.commands.utils import resolve_project_id
from bud.commands.config_store import set_config_value
from bud.schemas.project import ProjectCreate, ProjectUpdate
from bud.services import projects as project_service


@click.group()
def project():
    """Manage projects."""
    pass


@project.command("list")
def list_projects():
    """List all projects."""
    async def _run():
        async with get_session() as db:
            items = await project_service.list_projects(db)
            if not items:
                click.echo("No projects found.")
                return
            rows = [[str(p.id), p.name, "Yes" if p.is_default else ""] for p in items]
            click.echo(tabulate(rows, headers=["ID", "Name", "Default"], tablefmt="psql"))

    run_async(_run())


@project.command("create")
@click.option("--name", required=True, help="Project name")
def create_project(name):
    """Create a new project."""
    async def _run():
        async with get_session() as db:
            p = await project_service.create_project(db, ProjectCreate(name=name))
            click.echo(f"Created project: {p.name} (id: {p.id})")

    run_async(_run())


@project.command("edit")
@click.argument("project_id")
@click.option("--name", default=None)
def edit_project(project_id, name):
    """Edit a project. PROJECT_ID can be a UUID or project name."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo(f"Project not found: {project_id}", err=True)
                return
            p = await project_service.update_project(db, pid, ProjectUpdate(name=name))
            if not p:
                click.echo("Project not found.", err=True)
                return
            click.echo(f"Updated project: {p.name}")

    run_async(_run())


@project.command("delete")
@click.argument("project_id")
@click.confirmation_option(prompt="Delete this project?")
def delete_project(project_id):
    """Delete a project. PROJECT_ID can be a UUID or project name."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo(f"Project not found: {project_id}", err=True)
                return
            ok = await project_service.delete_project(db, pid)
            if not ok:
                click.echo("Project not found.", err=True)
                return
            click.echo("Project deleted.")

    run_async(_run())


@project.command("set-default")
@click.argument("project_id")
def set_default(project_id):
    """Set the default project. PROJECT_ID can be a UUID or project name."""
    async def _run():
        async with get_session() as db:
            pid = await resolve_project_id(db, project_id)
            if not pid:
                click.echo(f"Project not found: {project_id}", err=True)
                return
            p = await project_service.set_default_project(db, pid)
            if not p:
                click.echo("Project not found.", err=True)
                return
            set_config_value("default_project_id", str(p.id))
            click.echo(f"Default project set to: {p.name}")

    run_async(_run())
