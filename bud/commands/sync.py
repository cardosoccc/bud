"""Push and pull commands for syncing the database with cloud storage."""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import click

from bud.commands.config_store import CONFIG_DIR, DB_PATH, get_config_value

SYNC_META_FILE = CONFIG_DIR / "sync_meta.json"
REMOTE_DB_KEY = "bud.db"
REMOTE_META_KEY = "sync_meta.json"


def _load_local_meta() -> dict:
    if SYNC_META_FILE.exists():
        with open(SYNC_META_FILE) as f:
            return json.load(f)
    return {"version": 0}


def _save_local_meta(meta: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(SYNC_META_FILE, "w") as f:
        json.dump(meta, f, indent=2)


def _get_bucket_url() -> str:
    url = get_config_value("bucket")
    if not url:
        click.echo(
            "error: no bucket configured. set one with:\n"
            '  bud config set bucket s3://my-bucket/path\n'
            '  bud config set bucket gs://my-bucket/path',
            err=True,
        )
        sys.exit(1)
    return url


def _handle_auth_error(err) -> None:
    """Print a user-friendly authentication error and exit."""
    click.echo(
        f"error: {err.provider} authentication failed.\n"
        f"  {err}\n\n"
        f"to configure {err.provider} credentials, run:\n"
        f"  {err.configure_hint}",
        err=True,
    )
    sys.exit(1)


def run_push(force: bool = False) -> bool:
    """Push the local database to cloud storage.

    Returns True on success, False on failure (after printing an error).
    Raises CloudAuthError on authentication failures.
    """
    from bud.services.storage import get_provider

    if not DB_PATH.exists():
        click.echo("error: local database does not exist. run `bud db init` first.", err=True)
        return False

    url = get_config_value("bucket")
    if not url:
        click.echo("auto-push skipped: no bucket configured.", err=True)
        return False

    provider = get_provider(url)

    local_meta = _load_local_meta()
    local_version = local_meta.get("version", 0)

    remote_meta = provider.read_json(REMOTE_META_KEY)
    remote_version = remote_meta.get("version", 0) if remote_meta else 0

    if remote_version > local_version and not force:
        click.echo(
            f"error: remote version ({remote_version}) is newer than local ({local_version}).\n"
            "pull the latest version first, or use --force to overwrite.",
            err=True,
        )
        return False

    new_version = max(local_version, remote_version) + 1
    new_meta = {"version": new_version, "pushed_at": time.time()}

    provider.upload(DB_PATH, REMOTE_DB_KEY)
    provider.upload_json(new_meta, REMOTE_META_KEY)
    _save_local_meta(new_meta)

    click.echo(f"pushed database to {url} (version {new_version}).")
    return True


@click.command("push")
@click.option("--force", "-f", is_flag=True, help="push even if remote has a newer version.")
def push(force: bool) -> None:
    """push the local database to cloud storage."""
    from bud.services.storage import CloudAuthError

    try:
        if not run_push(force=force):
            sys.exit(1)
    except CloudAuthError as exc:
        _handle_auth_error(exc)


@click.command("pull")
@click.option("--force", "-f", is_flag=True, help="pull even if local has a newer version.")
def pull(force: bool) -> None:
    """pull the database from cloud storage."""
    from bud.services.storage import CloudAuthError, get_provider

    bucket_url = _get_bucket_url()

    try:
        provider = get_provider(bucket_url)
    except CloudAuthError as exc:
        _handle_auth_error(exc)

    try:
        remote_meta = provider.read_json(REMOTE_META_KEY)
        if remote_meta is None:
            click.echo("error: no database found in remote storage. push first.", err=True)
            sys.exit(1)

        remote_version = remote_meta.get("version", 0)

        local_meta = _load_local_meta()
        local_version = local_meta.get("version", 0)

        if local_version > remote_version and not force:
            click.echo(
                f"error: local version ({local_version}) is newer than remote ({remote_version}).\n"
                "push your changes first, or use --force to overwrite.",
                err=True,
            )
            sys.exit(1)

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        if DB_PATH.exists():
            backup = DB_PATH.with_suffix(".db.bak")
            shutil.copy2(DB_PATH, backup)

        provider.download(REMOTE_DB_KEY, DB_PATH)
        _save_local_meta(remote_meta)

        click.echo(f"pulled database from {bucket_url} (version {remote_version}).")
    except CloudAuthError as exc:
        _handle_auth_error(exc)
