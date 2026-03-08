"""CLI configuration storage in ~/.bud/config.json."""
import json
from datetime import date
from pathlib import Path
from typing import Optional


CONFIG_DIR = Path.home() / ".bud"
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_PATH = CONFIG_DIR / "bud.db"
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
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


def get_db_url() -> str:
    return DB_URL
