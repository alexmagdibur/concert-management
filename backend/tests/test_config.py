import pytest
from pydantic import ValidationError

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
