from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = f"sqlite+aiosqlite:///{Path.home() / '.bud' / 'bud.db'}"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
