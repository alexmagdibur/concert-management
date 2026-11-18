"""Explicit test-data creation; no startup hooks or production fallbacks."""

import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.engine import Connection, make_url

from app.core.config import Settings
from app.core.database import Base
from app.models import entities  # noqa: F401

PREFIX = "seed:v1:"
STAMP = datetime(2026, 1, 1, tzinfo=UTC)
EXPECTED_COUNTS = {
    "employee": 2,
    "account": 2,
    "role": 2,
    "account_role": 2,
    "venue": 3,
    "counterparty": 3,
    "concert": 4,
    "contract": 4,
    "engagement": 1,
    "finance_category": 2,
    "finance_entry": 4,
    "audit_event": 4,
}


class SeedError(ValueError):
    pass


def validate_target(settings: Settings, url: str, *, confirmed: bool) -> None:
    if settings.app_env not in {"development", "test"} or not settings.seed_enabled:
        raise SeedError("Seed requires APP_ENV=development/test and SEED_ENABLED=true")
    if not confirmed:
        raise SeedError("Pass --confirm-test-data to explicitly authorize test data")
    target = make_url(url)
    if target.get_backend_name() != "postgresql":
        raise SeedError("Seed supports PostgreSQL only")
    if not (target.database or "").endswith(("_seed", "_test")):
        raise SeedError("Use a dedicated database ending in _seed or _test")


def _unusable_password_hash() -> str:
    # No fixed or published credentials: the random password is discarded.
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(secrets.token_bytes(32), salt=salt, n=16384, r=8, p=1)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def seed_plan() -> dict[str, list[dict]]:
    """Stable negative IDs avoid advancing/colliding with normal positive sequences."""
    plan = {name: [] for name in EXPECTED_COUNTS}

    def add(table: str, **values):
        if "version" in Base.metadata.tables[table].c:
            values.update(created_at=STAMP, updated_at=STAMP, version=1)
        plan[table].append(values)

    for identity, role in [(-91001, "MANAGER"), (-91002, "ADMIN")]:
        add("employee", id=identity, full_name=f"[SEED] Test {role}", position=role, active=True)
        add(
            "account",
            id=identity,
            employee_id=identity,
            login=f"seed_v1_{role.lower()}",
            password_hash=_unusable_password_hash(),
            active=True,
            session_tokens={},
        )
        add("role", id=identity, code=role, name=role)
        add("account_role", account_id=identity, role_id=identity)
    for i, city in enumerate(["Moscow", "Saint Petersburg", "Kazan"], start=1):
        add(
            "venue",
            id=-92000 - i,
            name=f"[SEED] Hall {i}",
            city=city,
            address=f"[SEED] Test address {i}",
            capacity=500 * i,
            archived=False,
        )
    for i, name in enumerate(["Organizer A", "Organizer B", "Sound contractor"], start=1):
        add("counterparty", id=-93000 - i, name=f"[SEED] {name}", kind="LEGAL", archived=False)
    # Seed vocabulary: NEGOTIATING / CONFIRMED / COMPLETED / CANCELLED (UC04).
    dates = [
        datetime(2027, 2, 1, 18, tzinfo=UTC),
        datetime(2027, 3, 1, 18, tzinfo=UTC),
        datetime(2026, 9, 1, 18, tzinfo=UTC),
        datetime(2027, 4, 1, 18, tzinfo=UTC),
    ]
    for i, status in enumerate(["NEGOTIATING", "CONFIRMED", "COMPLETED", "CANCELLED"], start=1):
        add(
            "concert",
            id=-94000 - i,
            name=f"[SEED] {status}",
            starts_at=dates[i - 1],
            ends_at=dates[i - 1] + timedelta(hours=2),
            venue_id=None if i == 1 else -92002,
            proposed_organizer_id=-93001,
            responsible_id=-91001,
            expense_budget=Decimal("100000.00"),
            status=status,
            cancel_reason="[SEED] Organizer cancellation" if i == 4 else None,
        )
    for i in [2, 3, 4]:
        add(
            "contract",
            id=-95000 - i,
            number=f"SEED-V1-MAIN-{i}",
            signed_on=date(2026, 1, 1),
            concert_id=-94000 - i,
            counterparty_id=-93001,
            kind="MAIN_SHOW",
            subject="[SEED] Show",
            amount=Decimal("500000.00"),
            direction="IN",
            status="ACTIVE",
        )
    add(
        "contract",
        id=-95010,
        number="SEED-V1-SERVICE",
        signed_on=date(2026, 1, 1),
        concert_id=-94003,
        counterparty_id=-93003,
        kind="SERVICE",
        subject="[SEED] Sound",
        amount=Decimal("40000.00"),
        direction="OUT",
        status="ACTIVE",
    )
    add(
        "engagement",
        id=-96001,
        concert_id=-94003,
        counterparty_id=-93003,
        description="[SEED] Sound production",
        due_at=dates[2],
        agreed_amount=Decimal("40000.00"),
        contract_id=-95010,
        status="COMPLETED",
    )
    for i, direction in enumerate(["IN", "OUT"], start=1):
        add(
            "finance_category",
            id=-97000 - i,
            code=f"SEED_V1_{direction}",
            name=f"[SEED] {direction}",
            normal_direction=direction,
            archived=False,
        )
    # NIRS control example + a separate VOID error. Net show result: 60000.00.
    for i, amount, direction, contract_id, category_id, original_id, status in [
        (1, "150000.00", "IN", -95003, -97001, None, "POSTED"),
        (2, "40000.00", "OUT", -95010, -97002, None, "POSTED"),
        (3, "50000.00", "OUT", -95003, -97001, -98001, "POSTED"),
        (4, "100.00", "IN", -95003, -97001, None, "VOID"),
    ]:
        add(
            "finance_entry",
            id=-98000 - i,
            concert_id=-94003,
            contract_id=contract_id,
            category_id=category_id,
            occurred_on=date(2026, 9, i),
            amount=Decimal(amount),
            direction=direction,
            basis=f"[SEED] Paper document {i}",
            original_id=original_id,
            status=status,
            void_reason="[SEED] Input error" if status == "VOID" else None,
            created_by=-91001,
            posted_at=dates[2] + timedelta(days=i),
            request_key=f"{PREFIX}{i}",
        )
    for i in range(1, 5):
        add(
            "audit_event",
            id=-99000 - i,
            occurred_at=STAMP,
            actor_id=-91001,
            object_type="concert",
            object_id=-94000 - i,
            action="SEED_CREATE",
            before_data=None,
            after_data={"status": plan["concert"][i - 1]["status"]},
            reason="Explicit test-data seed v1",
        )
    return plan


def seed_connection(conn: Connection, settings: Settings, *, confirmed: bool) -> dict[str, int]:
    """Caller owns one transaction; refuse any unexpected data rather than overwrite it."""
    validate_target(
        settings, conn.engine.url.render_as_string(hide_password=False), confirmed=confirmed
    )
    if not conn.in_transaction():
        raise SeedError("Seed must run inside an explicit transaction")
    conn.execute(text("SELECT pg_advisory_xact_lock(731092011)"))
    # Block concurrent writes while inspecting and filling the dedicated database.
    conn.execute(
        text("LOCK TABLE " + ", ".join(sorted(EXPECTED_COUNTS)) + " IN SHARE ROW EXCLUSIVE MODE")
    )
    plan = seed_plan()
    for table in Base.metadata.sorted_tables:
        expected = plan[table.name]
        pk = [column.name for column in table.primary_key]
        lookup = {tuple(row[key] for key in pk): row for row in expected}
        for actual in conn.execute(select(table)).mappings():
            wanted = lookup.get(tuple(actual[key] for key in pk))
            if wanted is None:
                raise SeedError(
                    f"Unexpected existing data in {table.name}; use an empty seed database"
                )
            for key in actual:
                if key == "password_hash":
                    if not actual[key].startswith("scrypt$16384$8$1$"):
                        raise SeedError("Seed account hash was modified")
                elif actual[key] != wanted.get(key):
                    raise SeedError(
                        f"Existing seed row differs: {table.name}.{key}; no changes committed"
                    )
        existing = {tuple(row) for row in conn.execute(select(*table.primary_key.columns))}
        for row in expected:
            if tuple(row[key] for key in pk) not in existing:
                conn.execute(table.insert().values(**row))
    return {
        name: conn.scalar(select(func.count()).select_from(Base.metadata.tables[name]))
        for name in sorted(EXPECTED_COUNTS)
    }
