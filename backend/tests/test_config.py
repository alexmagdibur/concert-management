import pytest
from pydantic import ValidationError
from sqlalchemy import make_url

from app.core.config import Settings


def test_settings_from_environment(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Test CRM")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://localhost/test_crm")
    settings = Settings(_env_file=None)
    assert settings.app_name == "Test CRM"
    assert settings.database_url.path == "/test_crm"


def test_rejects_non_postgresql_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_container_database_settings_preserve_password(monkeypatch):
    password = "space and @:/@#?%+$"
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", password)
    monkeypatch.setenv("POSTGRES_USER", "crm_user")
    monkeypatch.setenv("POSTGRES_DB", "crm_database")
    settings = Settings(_env_file=None)
    url = make_url(str(settings.database_url))
    assert (url.host, url.port, url.username, url.database) == (
        "postgres",
        5432,
        "crm_user",
        "crm_database",
    )
    assert url.password == password


def test_container_database_requires_password(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "")
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD is required"):
        Settings(_env_file=None)
