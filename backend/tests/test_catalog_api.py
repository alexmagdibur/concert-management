import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from auth_support import NO_SESSION, login, session_headers, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import hash_password
from app.main import app
from app.models.entities import (
    Account,
    AccountRole,
    AuditEvent,
    Concert,
    Contract,
    Counterparty,
    Employee,
    FinanceCategory,
    FinanceEntry,
    Role,
    Venue,
)

CASES = [
    ("venue", {"name": "Hall", "city": "Moscow", "address": "Street", "capacity": 500}, Venue),
    ("counterparty", {"name": "Organizer", "kind": "LEGAL", "phone": "+123"}, Counterparty),
    ("finance_category", {"code": "FEE", "name": "Fee", "normal_direction": "IN"}, FinanceCategory),
]


@pytest.fixture
def api(db):
    conn, _ = db
    outer = conn.begin()
    setup = Session(bind=conn, join_transaction_mode="create_savepoint")
    now = datetime.now(UTC)
    password = secrets.token_urlsafe(24)
    identities = {}
    for i, role_code in enumerate(["MANAGER", "ADMIN"], start=1):
        employee = Employee(
            full_name=role_code,
            position=role_code,
            active=True,
            created_at=now,
            updated_at=now,
            version=1,
        )
        role = Role(code=role_code, name=role_code)
        setup.add_all([employee, role])
        setup.flush()
        account = Account(
            employee_id=employee.id,
            login=f"test_{role_code}",
            password_hash=hash_password(password),
            active=True,
        )
        setup.add(account)
        setup.flush()
        setup.add(AccountRole(account_id=account.id, role_id=role.id))
        identities[role_code] = (account.id, employee.id)
    setup.commit()

    def override_session():
        with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app, base_url="https://testserver") as client:
            sign_in(client, "test_MANAGER", password)
            yield client, setup, identities, password
    finally:
        app.dependency_overrides.pop(get_session, None)
        setup.close()
        outer.rollback()


@pytest.mark.parametrize("module,payload,model", CASES)
def test_crud_search_pagination_and_archive(api, module, payload, model):
    client, session, identities, _ = api
    root = "/" + module
    response = client.post(root, json=payload)
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["version"] == 1 and row["archived"] is False
    assert set(row) == {"id", "archived", "created_at", "updated_at", "version"} | {
        column.name for column in model.__table__.columns
    }
    assert client.get(f"{root}/{row['id']}").json() == row
    page = client.get(root, params={"q": payload["name"].lower(), "limit": 1}).json()
    assert page["total"] == 1 and len(page["items"]) == 1
    assert client.get(root, params={"offset": 1}).json()["items"] == []
    updated = client.patch(f"{root}/{row['id']}", json={"version": 1, "name": "Changed"})
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert (
        client.patch(f"{root}/{row['id']}", json={"version": 1, "name": "Stale"}).status_code == 409
    )
    archive = client.post(f"{root}/{row['id']}/archive", json={"version": 2})
    assert archive.status_code == 200 and archive.json()["archived"] is True
    assert client.get(root).json()["total"] == 0
    assert client.get(root, params={"archived": True}).json()["total"] == 1
    assert client.get(f"{root}/{row['id']}").status_code == 200
    assert client.delete(f"{root}/{row['id']}").status_code == 405
    assert client.post(f"{root}/{row['id']}/archive", json={"version": 3}).json()["version"] == 3
    assert session.get(model, row["id"]) is not None
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.object_type == module).order_by(AuditEvent.id)
    ).all()
    assert [e.action for e in events] == ["CREATE", "UPDATE", "ARCHIVE"]
    assert all(e.actor_id == identities["MANAGER"][0] for e in events)
    assert events[1].before_data["name"] == payload["name"]
    assert events[1].after_data["name"] == "Changed"


@pytest.mark.parametrize("module,payload,model", CASES)
def test_duplicates_missing_records_and_invalid_input(api, module, payload, model):
    client, session, _, _ = api
    root = "/" + module
    first = client.post(root, json=payload).json()
    duplicate = {**payload, "name": payload["name"].upper()}
    if "code" in payload:
        duplicate["code"] = payload["code"].lower()
    assert client.post(root, json=duplicate).status_code == 409
    assert client.post(root, json={**payload, "name": " "}).status_code == 422
    assert client.post(root, json={**payload, "archived": True}).status_code == 422
    assert client.post(root, json={**payload, "name": "X" * 201}).status_code == 422
    assert client.patch(f"{root}/{first['id']}", json={"version": 1}).status_code == 422
    assert (
        client.patch(f"{root}/{first['id']}", json={"version": 1, "name": None}).status_code == 422
    )
    assert client.patch(f"{root}/{first['id']}", json={"name": "New"}).status_code == 422
    for params in [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"q": ""}]:
        assert client.get(root, params=params).status_code == 422
    for method, body in [("get", None), ("patch", {"version": 1, "name": "Unknown"})]:
        response = getattr(client, method)(root + "/999999", **({"json": body} if body else {}))
        assert response.status_code == 404
    assert client.post(root + "/999999/archive", json={"version": 1}).status_code == 404
    assert client.get(root + "/9223372036854775808").status_code == 422
    assert session.scalar(select(func.count()).select_from(model)) == 1


@pytest.mark.parametrize("module,payload,model", CASES)
def test_duplicate_updates_and_archived_duplicates(api, module, payload, model):
    client, _, _, _ = api
    root = "/" + module
    first = client.post(root, json=payload).json()
    other = dict(payload, name="Other")
    if module == "venue":
        other["address"] = "Other street"
    elif module == "finance_category":
        other["code"] = "OTHER"
    second = client.post(root, json=other).json()
    assert (
        client.patch(root + f"/{second['id']}", json={**payload, "version": 1}).status_code == 409
    )
    assert client.post(root + f"/{first['id']}/archive", json={"version": 1}).status_code == 200
    assert client.post(root, json=payload).status_code == 409


@pytest.mark.parametrize("module,payload,model", CASES)
def test_sessions_and_roles(api, module, payload, model):
    client, session, identities, password = api
    root = "/" + module
    assert client.get(root, headers=NO_SESSION).status_code == 401
    assert login(client, "test_MANAGER", "wrong").status_code == 401
    assert login(client, "unknown", password).status_code == 401
    assert client.get(root, headers=session_headers("test_ADMIN", password)).status_code == 403
    account = session.get(Account, identities["MANAGER"][0])
    account.active = False
    session.commit()
    assert client.get(root).status_code == 401
    account.active = True
    employee = session.get(Employee, identities["MANAGER"][1])
    employee.active = False
    session.commit()
    assert client.get(root).status_code == 401


def test_validation_nullable_fields_and_literal_search(api):
    client, _, _, _ = api
    assert (
        client.post(
            "/venue", json={"name": "Hall", "city": "City", "address": "A", "capacity": -1}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/finance_category", json={"name": "Fee", "code": "F", "normal_direction": "BAD"}
        ).status_code
        == 422
    )
    response = client.post(
        "/counterparty", json={"name": "100%_party", "kind": "LEGAL", "phone": "123"}
    ).json()
    updated = client.patch(f"/counterparty/{response['id']}", json={"version": 1, "phone": None})
    assert updated.status_code == 200 and updated.json()["phone"] is None
    assert client.get("/counterparty", params={"q": "%_"}).json()["total"] == 1
    assert client.get("/counterparty", params={"q": "%' OR 1=1 --"}).json()["total"] == 0
    assert client.get("/counterparty", params={"q": "missing"}).json()["total"] == 0


def test_archive_preserves_real_concert_contract_and_finance_links(api):
    client, session, ids, _ = api
    venue = client.post("/venue", json={"name": "Hall", "city": "City", "address": "A"}).json()
    party = client.post("/counterparty", json={"name": "Organizer", "kind": "LEGAL"}).json()
    category = client.post(
        "/finance_category", json={"code": "FEE", "name": "Fee", "normal_direction": "IN"}
    ).json()
    now = datetime.now(UTC)
    technical = {"created_at": now, "updated_at": now, "version": 1}
    concert = Concert(
        name="Show",
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        venue_id=venue["id"],
        proposed_organizer_id=party["id"],
        responsible_id=ids["MANAGER"][1],
        expense_budget=Decimal("100.00"),
        status="NEGOTIATING",
        **technical,
    )
    session.add(concert)
    session.flush()
    contract = Contract(
        number="1",
        signed_on=now.date(),
        concert_id=concert.id,
        counterparty_id=party["id"],
        kind="MAIN_SHOW",
        subject="Show",
        amount=Decimal("100.00"),
        direction="IN",
        status="ACTIVE",
        **technical,
    )
    session.add(contract)
    session.flush()
    entry = FinanceEntry(
        concert_id=concert.id,
        contract_id=contract.id,
        category_id=category["id"],
        occurred_on=now.date(),
        amount=Decimal("10.00"),
        direction="IN",
        basis="Paper",
        status="POSTED",
        request_key="archive-test",
        created_by=ids["MANAGER"][0],
        posted_at=now,
        **technical,
    )
    session.add(entry)
    session.commit()
    for root, row in [("venue", venue), ("counterparty", party), ("finance_category", category)]:
        assert client.post(f"/{root}/{row['id']}/archive", json={"version": 1}).status_code == 200
    session.expire_all()
    assert session.get(Concert, concert.id).venue_id == venue["id"]
    assert session.get(Concert, concert.id).proposed_organizer_id == party["id"]
    assert session.get(Contract, contract.id).counterparty_id == party["id"]
    assert session.get(FinanceEntry, entry.id).category_id == category["id"]


def test_audit_failure_rolls_back_directory(api, monkeypatch):
    client, session, _, _ = api
    original = Session.flush

    def fail_audit(self, *args, **kwargs):
        if any(isinstance(row, AuditEvent) for row in self.new):
            raise SQLAlchemyError("Simulated audit write failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Session, "flush", fail_audit)
    with pytest.raises(SQLAlchemyError):
        client.post("/venue", json={"name": "Hall", "city": "City", "address": "A"})
    assert session.scalar(select(func.count()).select_from(Venue)) == 0
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_email_validation_and_optional_fields(api):
    client, _, _, _ = api
    payload = {"name": "Company", "kind": "LEGAL", "email": "invalid-email"}
    assert client.post("/counterparty", json=payload).status_code == 422
    payload["email"] = "info@example.com"
    created = client.post("/counterparty", json=payload)
    assert created.status_code == 201
    row = created.json()
    assert (
        client.patch(f"/counterparty/{row['id']}", json={"version": 1, "email": "bad"}).status_code
        == 422
    )
    assert (
        client.patch(f"/counterparty/{row['id']}", json={"version": 1, "email": None}).json()[
            "email"
        ]
        is None
    )


def test_search_fields_and_stable_pages(api):
    client, _, _, _ = api
    for i in range(3):
        assert (
            client.post(
                "/venue", json={"name": f"Hall{i}", "city": "Moscow", "address": f"Street{i}"}
            ).status_code
            == 201
        )
    pages = [
        client.get("/venue", params={"q": "MOSCOW", "limit": 1, "offset": i}).json()
        for i in range(3)
    ]
    assert all(page["total"] == 3 for page in pages)
    identities = [page["items"][0]["id"] for page in pages]
    assert identities == sorted(set(identities))
    assert client.get("/venue", params={"q": "Street1"}).json()["total"] == 1
    assert (
        client.post(
            "/counterparty", json={"name": "Company", "kind": "LEGAL", "email": "info@example.com"}
        ).status_code
        == 201
    )
    assert client.get("/counterparty", params={"q": "example.com"}).json()["total"] == 1
    assert (
        client.post(
            "/finance_category",
            json={"code": "RENT", "name": "Room cost", "normal_direction": "OUT"},
        ).status_code
        == 201
    )
    assert client.get("/finance_category", params={"q": "rent"}).json()["total"] == 1


def test_cyrillic_search_and_duplicate_detection(api):
    client, _, _, _ = api
    payload = {
        "name": "\u0417\u0430\u043b",
        "city": "\u041c\u043e\u0441\u043a\u0432\u0430",
        "address": "\u0423\u043b\u0438\u0446\u0430",
    }
    assert client.post("/venue", json=payload).status_code == 201
    assert client.get("/venue", params={"q": payload["city"].upper()}).json()["total"] == 1
    assert client.get("/venue", params={"q": payload["name"].lower()}).json()["total"] == 1
    assert (
        client.post(
            "/venue", json={key: value.upper() for key, value in payload.items()}
        ).status_code
        == 409
    )
