from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


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
    postgres_host: str | None = None
    postgres_user: str = "concert_crm"
    postgres_db: str = "concert_crm"
    postgres_password: SecretStr | None = None
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["lax", "strict"] = "lax"
    session_ttl_seconds: Annotated[int, Field(ge=60, le=86400)] = 28800

    @model_validator(mode="after")
    def configure_container_database(self):
        if self.postgres_host is not None:
            if self.postgres_password is None or not self.postgres_password.get_secret_value():
                raise ValueError("POSTGRES_PASSWORD is required when POSTGRES_HOST is set")
            url = URL.create(
                "postgresql+psycopg",
                username=self.postgres_user,
                password=self.postgres_password.get_secret_value(),
                host=self.postgres_host,
                port=5432,
                database=self.postgres_db,
                query={"connect_timeout": "3"},
            )
            self.database_url = PostgresDsn(url.render_as_string(hide_password=False))
        return self

    @model_validator(mode="after")
    def secure_production_cookie(self):
        if self.app_env == "production" and not self.session_cookie_secure:
            raise ValueError("Production requires Secure session cookies")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
