"""CLI configuration storage in ~/.bud/config.json."""
import json
import os
from pathlib import Path
from typing import Optional


CONFIG_DIR = Path.home() / ".bud"
CONFIG_FILE = CONFIG_DIR / "config.json"


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


def set_config_value(key: str, value) -> None:
    config = load_config()
    config[key] = value
    save_config(config)


def get_user_id() -> Optional[str]:
    return get_config_value("user_id")


def get_active_month() -> Optional[str]:
    return get_config_value("active_month")


def get_default_project_id() -> Optional[str]:
    return get_config_value("default_project_id")


def get_db_url() -> str:
    return get_config_value(
        "db_url",
        os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost/bud"),
    )
