"""CLI configuration storage in ~/.bud/users/<name>/config.json."""
import json
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

import click

_BUD_ROOT = Path.home() / ".bud"
_active_user: str = "default"

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_USERNAME_MAX_LEN = 64


def _validate_username(name: str) -> None:
    if not name or len(name) > _USERNAME_MAX_LEN or not _USERNAME_RE.match(name):
        raise click.BadParameter(
            f"Invalid user name {name!r}. "
            "Must be 1-64 characters, alphanumeric, hyphens, or underscores.",
            param_hint="'--user'",
        )


def _maybe_migrate_legacy_data() -> None:
    """Move legacy ~/.bud/ root files to ~/.bud/users/default/."""
    legacy_db = _BUD_ROOT / "bud.db"
    target_dir = _BUD_ROOT / "users" / "default"

    if not legacy_db.exists() or target_dir.exists():
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("bud.db", "config.json", "credentials.json", "sync_meta.json"):
        src = _BUD_ROOT / filename
        if src.exists():
            shutil.copy2(src, target_dir / filename)

    # Verify copy succeeded before removing originals
    if (target_dir / "bud.db").exists():
        for filename in ("bud.db", "config.json", "credentials.json", "sync_meta.json"):
            src = _BUD_ROOT / filename
            if src.exists():
                src.unlink()


def set_active_user(name: str) -> None:
    global _active_user
    _validate_username(name)
    _active_user = name
    if name == "default":
        _maybe_migrate_legacy_data()


def get_active_user() -> str:
    return _active_user


def get_config_dir() -> Path:
    return _BUD_ROOT / "users" / _active_user


def get_db_path() -> Path:
    return get_config_dir() / "bud.db"


def get_db_url() -> str:
    return f"sqlite+aiosqlite:///{get_db_path()}"


def get_config_file() -> Path:
    return get_config_dir() / "config.json"


def load_config() -> dict:
    config_file = get_config_file()
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)
    return {}


def save_config(config: dict) -> None:
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(get_config_file(), "w") as f:
        json.dump(config, f, indent=2)


def get_config_value(key: str, default=None):
    return load_config().get(key, default)


_KEY_ALIASES = {
    "month": "active_month",
    "auto-push": "auto_push",
}

_BOOL_KEYS = {"auto_push"}


def _coerce_value(key: str, value):
    """Coerce string values to appropriate types for known keys."""
    canonical = _KEY_ALIASES.get(key, key)
    if canonical in _BOOL_KEYS and isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    return value


def set_config_value(key: str, value) -> None:
    key = _KEY_ALIASES.get(key, key)
    value = _coerce_value(key, value)
    config = load_config()
    config[key] = value
    save_config(config)


def get_active_month() -> str:
    return get_config_value("active_month") or date.today().strftime("%Y-%m")


def get_default_project_id() -> Optional[str]:
    return get_config_value("default_project_id")


def get_auto_push() -> bool:
    return bool(get_config_value("auto_push", False))
