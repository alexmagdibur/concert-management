from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.database import Base
from app.services.seed import (
    EXPECTED_COUNTS,
    SeedError,
    seed_connection,
    seed_plan,
    validate_target,
)


@pytest.fixture
def seeded(db):
    conn, _ = db
    with conn.begin() as tx:
        settings = Settings(_env_file=None, app_env="test", seed_enabled=True)
        counts = seed_connection(conn, settings, confirmed=True)
        yield conn, settings, counts
        tx.rollback()


@pytest.mark.parametrize(
    "env,enabled,confirmed,url",
    [
        ("production", True, True, "postgresql://localhost/crm_seed"),
        ("test", False, True, "postgresql://localhost/crm_seed"),
        ("test", True, False, "postgresql://localhost/crm_seed"),
        ("test", True, True, "postgresql://localhost/crm"),
        ("test", True, True, "sqlite:///crm_seed"),
    ],
)
def test_guard_refuses(env, enabled, confirmed, url):
    settings = Settings(_env_file=None, app_env=env, seed_enabled=enabled)
    with pytest.raises(SeedError):
        validate_target(settings, url, confirmed=confirmed)


def test_seed_repeat_preserves_every_value(seeded):
    conn, settings, counts = seeded
    assert counts == EXPECTED_COUNTS
    before = {t.name: list(conn.execute(select(t)).mappings()) for t in Base.metadata.sorted_tables}
    assert seed_connection(conn, settings, confirmed=True) == counts
    after = {t.name: list(conn.execute(select(t)).mappings()) for t in Base.metadata.sorted_tables}
    assert before == after
    accounts = before["account"]
    assert accounts[0]["password_hash"].startswith("scrypt$")
    assert accounts[0]["password_hash"] != accounts[1]["password_hash"]


def test_real_business_links(seeded):
    conn, _, _ = seeded
    assert (
        conn.scalar(
            text("""SELECT count(*) FROM account a JOIN employee e ON a.employee_id=e.id
        JOIN account_role ar ON ar.account_id=a.id JOIN role r ON ar.role_id=r.id
        WHERE e.active AND a.active AND r.code IN ('ADMIN','MANAGER')""")
        )
        == 2
    )
    assert (
        conn.scalar(
            text("""SELECT count(*) FROM concert c JOIN venue v ON v.id=c.venue_id
        JOIN contract k ON k.concert_id=c.id AND k.counterparty_id=c.proposed_organizer_id
        WHERE c.status IN ('CONFIRMED','COMPLETED') AND k.kind='MAIN_SHOW'
        AND k.status='ACTIVE'""")
        )
        == 2
    )
    assert (
        conn.scalar(
            text("""SELECT count(*) FROM engagement e JOIN contract k
        ON e.contract_id=k.id WHERE e.concert_id=k.concert_id
        AND e.counterparty_id=k.counterparty_id AND e.agreed_amount=k.amount
        AND k.kind='SERVICE' AND k.direction='OUT'""")
        )
        == 1
    )
    assert (
        conn.scalar(
            text("""SELECT count(*) FROM finance_entry f JOIN contract k
        ON f.contract_id=k.id WHERE f.concert_id<>k.concert_id
        OR (f.original_id IS NULL AND f.direction<>k.direction)""")
        )
        == 0
    )
    assert (
        conn.scalar(
            text("""SELECT count(*) FROM finance_entry f JOIN finance_entry o
        ON f.original_id=o.id WHERE f.direction<>o.direction AND f.concert_id=o.concert_id
        AND f.contract_id=o.contract_id AND f.category_id=o.category_id
        AND f.amount<=o.amount AND o.status='POSTED'""")
        )
        == 1
    )
    result = conn.scalar(
        text("""SELECT sum(CASE direction WHEN 'IN' THEN amount ELSE -amount END)
        FROM finance_entry WHERE status='POSTED'""")
    )
    assert result == Decimal("60000.00")
    assert (
        conn.scalar(
            text("""SELECT count(*) FROM concert a JOIN concert b ON a.id<b.id
        WHERE a.status='CONFIRMED' AND b.status='CONFIRMED'
        AND a.starts_at<b.ends_at AND b.starts_at<a.ends_at""")
        )
        == 0
    )


@pytest.mark.parametrize("table", sorted(EXPECTED_COUNTS))
def test_primary_keys_reject_duplicate_seed_rows(seeded, table):
    conn, _, _ = seeded
    model = Base.metadata.tables[table]
    row = dict(conn.execute(select(model)).mappings().first())
    with pytest.raises(IntegrityError) as exc, conn.begin_nested():
        conn.execute(model.insert().values(**row))
    assert exc.value.orig.sqlstate == "23505"
    assert exc.value.orig.diag.constraint_name == f"{table}_pkey"


FKS = [
    (table.name, fk.parent.name)
    for table in Base.metadata.sorted_tables
    for fk in table.foreign_keys
]


@pytest.mark.parametrize("table,column", FKS)
def test_all_foreign_keys_reject_missing_objects(seeded, table, column):
    conn, _, _ = seeded
    with pytest.raises(IntegrityError) as exc, conn.begin_nested():
        model = Base.metadata.tables[table]
        first = conn.execute(select(model)).mappings().first()
        predicate = [key == first[key.name] for key in model.primary_key]
        conn.execute(model.update().where(*predicate).values(**{column: -999999999}))
    assert exc.value.orig.sqlstate == "23503"


def test_modified_data_refused_without_overwrite(seeded):
    conn, settings, _ = seeded
    table = Base.metadata.tables["venue"]
    conn.execute(table.update().values(city="Changed"))
    with pytest.raises(SeedError), conn.begin_nested():
        seed_connection(conn, settings, confirmed=True)
    assert conn.scalar(select(table.c.city).limit(1)) == "Changed"


def test_partial_write_is_rolled_back(db):
    conn, _ = db
    settings = Settings(_env_file=None, app_env="test", seed_enabled=True)
    # A late table with an unexpected row makes the whole transaction fail.
    with pytest.raises(SeedError), conn.begin():
        plan = seed_plan()
        category = dict(plan["finance_category"][0])
        category.update(id=-123, code="UNEXPECTED")
        conn.execute(Base.metadata.tables["finance_category"].insert().values(**category))
        seed_connection(conn, settings, confirmed=True)
    assert conn.scalar(text("SELECT count(*) FROM employee")) == 0
    assert conn.scalar(text("SELECT count(*) FROM finance_category")) == 0
    conn.rollback()
