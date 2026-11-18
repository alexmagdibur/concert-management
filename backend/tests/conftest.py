import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from concert_support import prepare
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.database import get_session
from app.main import app


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


@pytest.fixture
def concert_api(db):
    conn, _ = db
    outer = conn.begin()
    setup = Session(bind=conn, join_transaction_mode="create_savepoint")
    data = prepare(setup)
    setup.commit()

    def override():
        with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
            yield session

    app.dependency_overrides[get_session] = override
    try:
        with TestClient(app) as client:
            client.auth = ("test_MANAGER", data["password"])
            yield client, setup, data
    finally:
        app.dependency_overrides.pop(get_session, None)
        setup.close()
        outer.rollback()
