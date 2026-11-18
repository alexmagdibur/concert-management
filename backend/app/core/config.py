from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, model_validator
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
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["lax", "strict"] = "lax"
    session_ttl_seconds: Annotated[int, Field(ge=60, le=86400)] = 28800

    @model_validator(mode="after")
    def secure_production_cookie(self):
        if self.app_env == "production" and not self.session_cookie_secure:
            raise ValueError("Production requires Secure session cookies")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
