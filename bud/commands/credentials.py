"""CLI commands for configuring cloud provider credentials."""
from __future__ import annotations

import os

import click


@click.command("aws")
@click.option("--access-key-id", prompt="AWS Access Key ID", help="AWS access key ID.")
@click.option(
    "--secret-access-key",
    prompt="AWS Secret Access Key",
    hide_input=True,
    help="AWS secret access key.",
)
def configure_aws(access_key_id: str, secret_access_key: str) -> None:
    """Store AWS credentials for push/pull operations."""
    from bud.credentials import set_credential

    set_credential("aws_access_key_id", access_key_id)
    set_credential("aws_secret_access_key", secret_access_key)
    click.echo("AWS credentials saved.")


@click.command("gcp")
@click.option(
    "--key-file",
    prompt="Path to GCP service-account key file",
    help="Absolute path to a GCP service-account JSON key file.",
)
def configure_gcp(key_file: str) -> None:
    """Store GCP service-account key file path for push/pull operations."""
    path = os.path.expanduser(key_file)
    if not os.path.isfile(path):
        click.echo(f"Error: file not found: {path}", err=True)
        raise SystemExit(1)

    from bud.credentials import set_credential

    set_credential("gcp_service_account_key_file", os.path.abspath(path))
    click.echo("GCP credentials saved.")
