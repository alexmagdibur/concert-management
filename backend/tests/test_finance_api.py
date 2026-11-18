from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep

import pytest
from auth_support import NO_SESSION, session_headers, sign_in
from concert_support import payload
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.main import app
from app.models.entities import AuditEvent, FinanceEntry
from app.repositories.finance import FinanceRepository


def setup_records(client, data):
    concert = client.post("/concert", json=payload(data))
    assert concert.status_code == 201, concert.text
    categories = {}
    for direction in ("IN", "OUT"):
        response = client.post(
            "/finance_category",
            json={
                "name": f"Category {direction}",
                "code": f"CAT_{direction}",
                "normal_direction": direction,
            },
        )
        assert response.status_code == 201, response.text
        categories[direction] = response.json()["id"]
    return concert.json()["id"], categories


def operation(concert, category, **changes):
    return {
        "concert_id": concert,
        "category_id": category,
        "occurred_on": "2020-02-01",
        "direction": "IN",
        "amount": "123.45",
        "basis": "Bank statement",
    } | changes


def contract_for(client, concert, data):
    response = client.post(
        "/contract",
        json={
            "concert_id": concert,
            "counterparty_id": data["party1"],
            "number": f"MAIN-{concert}",
            "signed_on": "2020-01-01",
            "kind": "MAIN_SHOW",
            "direction": "IN",
            "subject": "Performance",
            "amount": "500000.00",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.parametrize("direction", ["IN", "OUT"])
def test_register_list_and_retry(concert_api, direction):
    client, session, data = concert_api
    concert, categories = setup_records(client, data)
    body = operation(concert, categories[direction], direction=direction, request_key="payment-1")
    contract = contract_for(client, concert, data) if direction == "IN" else None
    body["contract_id"] = contract
    result = client.post("/finance", json=body)
    assert result.status_code == 201, result.text
    row = result.json()
    assert row["status"] == "POSTED" and row["version"] == 1
    assert row["amount"] == "123.45" and row["posted_at"].endswith("Z")
    assert row["created_by"] == data["MANAGER"]["account"]
    assert row["contract_id"] == contract and row["request_key"] == "payment-1"
    repeat = client.post("/finance", json=body | {"amount": "123.450"})
    assert repeat.status_code == 200 and repeat.json() == row
    assert client.post("/finance", json=body | {"amount": "123.46"}).status_code == 409
    url = f"/concert/{concert}/finance"
    assert client.get(url, params={"status": "POSTED"}).json()["items"] == [row]
    assert client.get(url, params={"status": "DRAFT"}).json()["total"] == 0
    second = client.post("/concert", json=payload(data, shift=1)).json()["id"]
    assert client.get(f"/concert/{second}/finance").json()["total"] == 0
    assert client.get("/concert/999999/finance").status_code == 404
    if contract:
        assert client.get(f"/contract/{contract}").json()["amount"] == "500000.00"
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.object_type == "finance_entry")
    ).all()
    assert [event.action for event in events] == ["POST"]


def test_draft_post_and_void_preserve_history(concert_api):
    client, session, data = concert_api
    concert, categories = setup_records(client, data)
    body = operation(concert, categories["IN"])
    draft = client.post("/finance/draft", json=body)
    assert draft.status_code == 201
    row = draft.json()
    assert row["status"] == "DRAFT" and row["posted_at"] is None and row["request_key"] is None
    url = f"/finance/{row['id']}"
    edit = client.patch(url, json={"version": 1, "amount": "500.25", "basis": "Receipt"})
    assert edit.status_code == 200 and edit.json()["version"] == 2
    assert client.patch(url, json={"version": 1, "amount": "9"}).status_code == 409
    assert client.post(url + "/post", json={"version": 2}).status_code == 422
    assert client.post(url + "/void", json={"version": 2, "reason": "Error"}).status_code == 409
    key = {"version": 2, "request_key": "post-a-draft"}
    booked = client.post(url + "/post", json=key)
    assert booked.status_code == 200 and booked.json()["status"] == "POSTED"
    assert booked.json()["amount"] == "500.25" and booked.json()["version"] == 3
    assert client.post(url + "/post", json=key).json() == booked.json()
    assert client.patch(url, json={"version": 3, "amount": "1"}).status_code == 409
    assert client.delete(url).status_code == 405
    assert client.post(url + "/void", json={"version": 3, "reason": " "}).status_code == 422
    voided = client.post(url + "/void", json={"version": 3, "reason": "Wrong receipt"})
    assert voided.status_code == 200 and voided.json()["status"] == "VOID"
    assert voided.json()["amount"] == booked.json()["amount"]
    assert voided.json()["posted_at"] == booked.json()["posted_at"]
    assert voided.json()["request_key"] == booked.json()["request_key"]
    assert client.post(url + "/post", json=key).json() == voided.json()
    assert client.patch(url, json={"version": 4, "basis": "Replacement"}).status_code == 409
    history = client.get(f"/concert/{concert}/finance", params={"status": "VOID"}).json()
    assert history["items"] == [voided.json()]
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.object_type == "finance_entry").order_by(AuditEvent.id)
    ).all()
    assert [event.action for event in events] == ["CREATE", "UPDATE", "POST", "VOID"]
    assert events[-1].reason == "Wrong receipt"


def test_invalid_finance_links_and_payload(concert_api):
    client, session, data = concert_api
    concert, categories = setup_records(client, data)
    other = client.post("/concert", json=payload(data, shift=1)).json()["id"]
    other_contract = contract_for(client, other, data)
    contract = contract_for(client, concert, data)
    body = operation(concert, categories["IN"], request_key="validation")
    for changes in (
        {"concert_id": 99999},
        {"category_id": 99999},
        {"contract_id": 99999},
        {"contract_id": other_contract},
        {"category_id": categories["OUT"]},
        {"contract_id": contract, "category_id": categories["OUT"], "direction": "OUT"},
        {"occurred_on": "2999-01-01"},
        {"occurred_on": "2020-02-30"},
        {"occurred_on": "2020-02-01T00:00:00"},
        {"amount": "0"},
        {"amount": "1.001"},
        {"amount": "1000000000000"},
        {"basis": " "},
        {"direction": "OTHER"},
        {"request_key": " "},
        {"request_key": "a" * 81},
        {"status": "VOID"},
        {"created_by": 123},
        {"original_id": 1},
    ):
        assert client.post("/finance", json=body | changes).status_code == 422, changes
    assert client.post("/finance", json=operation(concert, categories["IN"])).status_code == 422
    assert client.post("/finance", json=body, headers=NO_SESSION).status_code == 401
    assert (
        client.post(
            "/finance", json=body, headers=session_headers("test_ADMIN", data["password"])
        ).status_code
        == 403
    )
    archived = client.post(f"/finance_category/{categories['IN']}/archive", json={"version": 1})
    assert archived.status_code == 200
    assert client.post("/finance", json=body).status_code == 422
    assert session.scalar(select(func.count()).select_from(FinanceEntry)) == 0


def test_draft_rechecks_references_at_post_and_keys_are_global(concert_api):
    client, _, data = concert_api
    concert, categories = setup_records(client, data)
    body = operation(concert, categories["IN"])
    row = client.post("/finance/draft", json=body).json()
    other = client.post("/finance/draft", json=body).json()
    posted = client.post("/finance", json=body | {"request_key": "in-use"})
    assert posted.status_code == 201
    assert (
        client.post(
            f"/finance/{row['id']}/post",
            json={
                "version": 1,
                "request_key": "in-use",
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/finance_category/{categories['IN']}/archive", json={"version": 1}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/finance/{other['id']}/post",
            json={
                "version": 1,
                "request_key": "free-key",
            },
        ).status_code
        == 422
    )
    items = client.get(f"/concert/{concert}/finance", params={"status": "DRAFT"}).json()["items"]
    assert items == [other, row]


@pytest.mark.parametrize("mode", ["register", "draft", "conflicting_payload"])
def test_same_key_race_over_api(race, mode):
    engine, data = race

    def override():
        with Session(engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            yield session

    app.dependency_overrides[get_session] = override
    try:
        with TestClient(app, base_url="https://testserver") as client:
            sign_in(client, "test_MANAGER", data["password"])
            concert, categories = setup_records(client, data)
            body = operation(concert, categories["IN"])
            url = "/finance"
            key = f"race-{mode}"
            if mode == "draft":
                draft = client.post("/finance/draft", json=body).json()
                url = f"/finance/{draft['id']}/post"
                body = {"version": 1}
            body["request_key"] = key
            with ThreadPoolExecutor(max_workers=2) as pool:
                with Session(engine) as blocker:
                    FinanceRepository(blocker).lock_request_key(key)
                    second = body | {"amount": "123.46"} if mode == "conflicting_payload" else body
                    futures = [pool.submit(client.post, url, json=item) for item in (body, second)]
                    deadline = monotonic() + 5
                    while monotonic() < deadline:
                        with Session(engine) as observer:
                            waiting = observer.scalar(
                                text("""
                                SELECT count(DISTINCT waiter.pid)
                                FROM pg_locks waiter JOIN pg_locks owner
                                  USING (locktype, database, classid, objid, objsubid)
                                WHERE owner.pid = :pid AND owner.granted AND NOT waiter.granted
                                  AND waiter.locktype = 'advisory'
                            """),
                                {"pid": blocker.scalar(text("SELECT pg_backend_pid()"))},
                            )
                        if waiting == 2:
                            break
                        sleep(0.01)
                    assert waiting == 2
                    blocker.commit()
                responses = [future.result(timeout=15) for future in futures]
            expected = {
                "register": [200, 201],
                "draft": [200, 200],
                "conflicting_payload": [201, 409],
            }
            assert sorted(r.status_code for r in responses) == expected[mode]
            if mode != "conflicting_payload":
                assert responses[0].json() == responses[1].json()
            with Session(engine) as session:
                assert session.scalar(select(func.count()).select_from(FinanceEntry)) == 1
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(AuditEvent)
                        .where(
                            AuditEvent.object_type == "finance_entry",
                            AuditEvent.action == "POST",
                        )
                    )
                    == 1
                )
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_posted_operation_protects_contract_direction(concert_api):
    client, _, data = concert_api
    concert, categories = setup_records(client, data)
    contract = contract_for(client, concert, data)
    result = client.post(
        "/finance",
        json=operation(
            concert,
            categories["IN"],
            contract_id=contract,
            request_key="guard-direction",
        ),
    )
    assert result.status_code == 201
    conflict = client.patch(
        f"/contract/{contract}",
        json={
            "version": 1,
            "kind": "SERVICE",
            "direction": "OUT",
        },
    )
    assert conflict.status_code == 409
    assert client.get(f"/contract/{contract}").json()["direction"] == "IN"


def test_audit_failure_rolls_back_registration_and_releases_key(concert_api, monkeypatch):
    client, session, data = concert_api
    concert, categories = setup_records(client, data)
    body = operation(concert, categories["IN"], request_key="retry-after-rollback")
    flush = Session.flush

    def reject_audit(self, *args, **kwargs):
        if any(isinstance(row, AuditEvent) for row in self.new):
            raise SQLAlchemyError("audit failure")
        return flush(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "flush", reject_audit)
        with pytest.raises(SQLAlchemyError, match="audit failure"):
            client.post("/finance", json=body)
    assert client.get(f"/concert/{concert}/finance").json()["total"] == 0
    session.commit()
    assert client.post("/finance", json=body).status_code == 201
