import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command


@pytest.fixture(scope="module")
def db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a PostgreSQL test database")
    engine = create_engine(url)
    schema = "test_" + uuid4().hex
    with engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.execute(text(f'SET search_path TO "{schema}"'))
        conn.commit()
        cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        cfg.attributes["connection"] = conn
        try:
            command.upgrade(cfg, "head")
            conn.commit()
            command.upgrade(cfg, "head")
            conn.commit()
            yield conn, cfg
        finally:
            conn.rollback()
            conn.execute(text("SET search_path TO public"))
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            conn.commit()
    engine.dispose()
