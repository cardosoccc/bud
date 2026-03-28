"""Credential storage for cloud providers.

Credentials are stored in ~/.bud/credentials.json with restricted
file permissions (0600) to keep secrets out of the main config file.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional

from bud.commands.config_store import get_config_dir


def _get_credentials_file() -> Path:
    return get_config_dir() / "credentials.json"


def load_credentials() -> dict:
    """Load the credentials file, returning an empty dict if absent."""
    creds_file = _get_credentials_file()
    if creds_file.exists():
        with open(creds_file) as f:
            return json.load(f)
    return {}


def save_credentials(creds: dict) -> None:
    """Persist credentials to disk with owner-only read/write permissions."""
    get_config_dir().mkdir(parents=True, exist_ok=True)
    creds_file = _get_credentials_file()
    with open(creds_file, "w") as f:
        json.dump(creds, f, indent=2)
    os.chmod(creds_file, stat.S_IRUSR | stat.S_IWUSR)


def set_credential(key: str, value: str) -> None:
    creds = load_credentials()
    creds[key] = value
    save_credentials(creds)


def get_credential(key: str, default: Optional[str] = None) -> Optional[str]:
    return load_credentials().get(key, default)


# ---- AWS helpers -----------------------------------------------------------

def get_aws_credentials() -> Optional[tuple[str, str]]:
    """Return (access_key_id, secret_access_key) or None if not configured."""
    creds = load_credentials()
    key_id = creds.get("aws_access_key_id")
    secret = creds.get("aws_secret_access_key")
    if key_id and secret:
        return key_id, secret
    return None


# ---- GCP helpers -----------------------------------------------------------

def get_gcp_credentials_path() -> Optional[str]:
    """Return the path to the GCP service-account key file, or None."""
    return load_credentials().get("gcp_service_account_key_file")
