from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    app_env: Literal["production", "development", "test"] = "production"
    seed_enabled: bool = False
    seed_database_url: PostgresDsn | None = None
    app_name: str = "Concert CRM"
    database_url: PostgresDsn = "postgresql+psycopg://localhost:5432/concert_crm"


@lru_cache
def get_settings() -> Settings:
    return Settings()
