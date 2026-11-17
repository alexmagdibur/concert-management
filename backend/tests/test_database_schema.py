"""PostgreSQL-only tests, in a disposable schema; never modify application rows."""

import os
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import BigInteger, DateTime, Numeric, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app import models  # noqa: F401
from app.core.database import Base

TABLES = {
    "employee",
    "account",
    "role",
    "account_role",
    "venue",
    "counterparty",
    "concert",
    "engagement",
    "contract",
    "finance_category",
    "finance_entry",
    "audit_event",
}


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
def rows(db):
    conn, _ = db
    tx = conn.begin()
    now = datetime.now(UTC)
    values = {
        "employee": {"full_name": "Manager", "position": "Manager", "active": True},
        "account": {"employee_id": 1, "login": "manager", "password_hash": "hash", "active": True},
        "role": {"code": "ADMIN", "name": "Administrator"},
        "account_role": {"account_id": 1, "role_id": 1},
        "venue": {"name": "Hall", "city": "Moscow", "address": "Address", "archived": False},
        "counterparty": {"name": "Organizer", "kind": "LEGAL", "archived": False},
        "concert": {
            "name": "Show",
            "starts_at": now,
            "ends_at": now.replace(year=now.year + 1),
            "responsible_id": 1,
            "venue_id": 1,
            "expense_budget": Decimal("100.00"),
            "status": "DRAFT",
        },
        "contract": {
            "number": "1",
            "signed_on": date.today(),
            "concert_id": 1,
            "counterparty_id": 1,
            "kind": "MAIN_SHOW",
            "subject": "Show",
            "amount": Decimal("100.00"),
            "direction": "IN",
            "status": "ACTIVE",
        },
        "engagement": {
            "concert_id": 1,
            "counterparty_id": 1,
            "description": "Work",
            "due_at": now,
            "agreed_amount": Decimal("50.00"),
            "status": "DRAFT",
        },
        "finance_category": {
            "code": "FEE",
            "name": "Fee",
            "normal_direction": "IN",
            "archived": False,
        },
        "finance_entry": {
            "concert_id": 1,
            "contract_id": 1,
            "category_id": 1,
            "occurred_on": date.today(),
            "amount": Decimal("10.25"),
            "direction": "IN",
            "basis": "Document",
            "status": "POSTED",
            "request_key": "request-1",
            "posted_at": now,
            "created_by": 1,
        },
        "audit_event": {
            "occurred_at": now,
            "actor_id": 1,
            "object_type": "concert",
            "object_id": 1,
            "action": "CREATE",
        },
    }
    for table in Base.metadata.sorted_tables:
        row = values[table.name]
        if "id" in table.c:
            row["id"] = 1
        if "version" in table.c:
            row.update(created_at=now, updated_at=now, version=1)
        conn.execute(table.insert().values(**row))
    try:
        yield conn, values
    finally:
        tx.rollback()


def test_tables_and_physical_types(db):
    conn, _ = db
    inspector = inspect(conn)
    assert set(inspector.get_table_names()) == TABLES | {"alembic_version"}
    for name in TABLES:
        columns = {c["name"]: c for c in inspector.get_columns(name)}
        for col, info in columns.items():
            if col == "id" or col.endswith("_id") or col in {"version", "created_by"}:
                assert isinstance(info["type"], BigInteger), (name, col)
            if col in {"amount", "agreed_amount", "expense_budget"}:
                typ = info["type"]
                assert isinstance(typ, Numeric) and (typ.precision, typ.scale) == (14, 2)
            if col.endswith("_at"):
                assert isinstance(info["type"], DateTime) and info["type"].timezone
        for fk in inspector.get_foreign_keys(name):
            assert fk["options"].get("ondelete") == "RESTRICT"
    conn.rollback()


@pytest.mark.parametrize(
    "table,changes",
    [
        ("employee", {"full_name": None}),
        ("role", {"code": "UNKNOWN"}),
        ("account", {"employee_id": 999}),
        ("concert", {"expense_budget": Decimal("-0.01")}),
        ("concert", {"ends_at": datetime(2000, 1, 1, tzinfo=UTC)}),
        ("contract", {"amount": 0}),
        ("contract", {"kind": "TICKET"}),
        ("contract", {"direction": "BAD"}),
        ("engagement", {"agreed_amount": -1}),
        ("finance_category", {"normal_direction": "BAD"}),
        ("finance_entry", {"amount": 0}),
        ("finance_entry", {"direction": "BAD"}),
        ("finance_entry", {"status": "BAD"}),
        ("finance_entry", {"request_key": None}),
        ("finance_entry", {"status": "VOID", "void_reason": " "}),
        ("finance_entry", {"original_id": 999}),
    ],
)
def test_invalid_values_rejected(rows, table, changes):
    conn, _ = rows
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(Base.metadata.tables[table].update().values(**changes))


@pytest.mark.parametrize(
    "table", ["account", "role", "account_role", "finance_category", "finance_entry", "contract"]
)
def test_unique_constraints(rows, table):
    conn, values = rows
    row = dict(values[table])
    if "id" in row:
        row["id"] = 2
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(Base.metadata.tables[table].insert().values(**row))


def test_only_one_active_main_contract(rows):
    conn, values = rows
    row = dict(values["contract"], id=2, number="2")
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(Base.metadata.tables["contract"].insert().values(**row))
    row["status"] = "DRAFT"
    conn.execute(Base.metadata.tables["contract"].insert().values(**row))


@pytest.mark.parametrize(
    "table", ["concert", "contract", "account", "employee", "finance_category"]
)
def test_referenced_rows_cannot_be_deleted(rows, table):
    conn, _ = rows
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(Base.metadata.tables[table].delete())


def test_decimal_roundtrip_and_repeat_upgrade(rows, db):
    conn, cfg = db
    assert conn.execute(
        text("SELECT amount FROM finance_entry WHERE id=1")
    ).scalar_one() == Decimal("10.25")
    command.upgrade(cfg, "head")
    assert conn.execute(text("SELECT count(*) FROM finance_entry")).scalar_one() == 1


def test_nullable_request_keys_and_original_delete(rows):
    conn, values = rows
    table = Base.metadata.tables["finance_entry"]
    for identity in (2, 3):
        conn.execute(
            table.insert().values(
                **dict(
                    values["finance_entry"],
                    id=identity,
                    request_key=None,
                    status="DRAFT",
                    original_id=1,
                )
            )
        )
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(table.delete().where(table.c.id == 1))


def test_engagement_contract_is_unique(rows):
    conn, values = rows
    table = Base.metadata.tables["engagement"]
    conn.execute(table.update().values(contract_id=1))
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(table.insert().values(**dict(values["engagement"], id=2, contract_id=1)))


def test_contract_document_identity_is_unique(rows):
    conn, values = rows
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(Base.metadata.tables["contract"].insert().values(
            **dict(values["contract"], id=2, status="DRAFT")))
