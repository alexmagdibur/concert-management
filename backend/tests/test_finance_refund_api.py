from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from test_finance_api import contract_for, operation, setup_records

from app.core.database import get_session
from app.main import app
from app.models.entities import AuditEvent, FinanceEntry
from app.repositories.finance import FinanceRepository


def register(client, concert, category, **changes):
    result = client.post(
        "/finance", json=operation(concert, category, request_key="source") | changes
    )
    assert result.status_code == 201, result.text
    return result.json()


def refund_body(amount, key="refund-1", **changes):
    return {
        "occurred_on": "2020-02-02",
        "amount": amount,
        "basis": "Bank reversal",
        "request_key": key,
    } | changes


def test_full_refund_preserves_original_and_links(concert_api):
    client, session, data = concert_api
    concert, categories = setup_records(client, data)
    contract = contract_for(client, concert, data)
    source = register(client, concert, categories["IN"], contract_id=contract)
    assert (
        client.post(
            f"/finance_category/{categories['IN']}/archive", json={"version": 1}
        ).status_code
        == 200
    )
    response = client.post(f"/finance/{source['id']}/refund", json=refund_body("123.45"))
    assert response.status_code == 201, response.text
    refund = response.json()
    assert refund["id"] != source["id"]
    assert refund["original_id"] == source["id"]
    assert refund["status"] == "POSTED" and refund["direction"] == "OUT"
    assert refund["posted_at"] and refund["created_by"] == source["created_by"]
    for field in ("concert_id", "category_id", "contract_id", "amount"):
        assert refund[field] == source[field]
    items = client.get(f"/concert/{concert}/finance").json()["items"]
    assert items == [refund, source]
    assert client.get(f"/concert/{concert}/finance/totals").json() == {
        "income": "123.45",
        "expenses": "123.45",
        "net": "0.00",
    }
    audit = session.scalar(
        select(AuditEvent).where(
            AuditEvent.object_type == "finance_entry",
            AuditEvent.action == "REFUND",
        )
    )
    assert audit.object_id == refund["id"] and audit.after_data["original_id"] == source["id"]


def test_partial_refunds_and_excess(concert_api):
    client, _, data = concert_api
    concert, categories = setup_records(client, data)
    source = register(client, concert, categories["OUT"], direction="OUT")
    url = f"/finance/{source['id']}/refund"
    first = client.post(url, json=refund_body("40.10"))
    assert first.status_code == 201 and first.json()["direction"] == "IN"
    assert first.json()["contract_id"] is None
    conflict = client.post(url, json=refund_body("83.36", "refund-2"))
    assert conflict.status_code == 409 and "83.35" in conflict.json()["detail"]
    second = client.post(url, json=refund_body("83.35", "refund-2"))
    assert second.status_code == 201
    assert client.post(url, json=refund_body("0.01", "refund-3")).status_code == 409
    assert client.get(f"/concert/{concert}/finance").json()["total"] == 3


def test_void_retains_entry_excludes_it_from_totals_and_blocks_refund(concert_api):
    client, _, data = concert_api
    concert, categories = setup_records(client, data)
    source = register(client, concert, categories["IN"])
    register(
        client, concert, categories["OUT"], direction="OUT", amount="4.50", request_key="other"
    )
    draft = client.post("/finance/draft", json=operation(concert, categories["IN"]))
    assert draft.status_code == 201
    url = f"/finance/{source['id']}"
    assert client.post(url + "/void", json={"version": 1}).status_code == 422
    voided = client.post(url + "/void", json={"version": 1, "reason": "Duplicate receipt"})
    assert voided.status_code == 200 and voided.json()["status"] == "VOID"
    assert voided.json()["amount"] == source["amount"]
    assert voided.json()["void_reason"] == "Duplicate receipt"
    assert client.post(url + "/void", json={"version": 2, "reason": "Again"}).status_code == 409
    assert client.post(url + "/refund", json=refund_body("1")).status_code == 409
    assert client.get(f"/concert/{concert}/finance", params={"status": "VOID"}).json()["items"] == [
        voided.json()
    ]
    assert client.get(f"/concert/{concert}/finance/totals").json() == {
        "income": "0.00",
        "expenses": "4.50",
        "net": "-4.50",
    }


def test_refund_retry_and_keys(concert_api):
    client, _, data = concert_api
    concert, categories = setup_records(client, data)
    source = register(client, concert, categories["IN"])
    other = register(client, concert, categories["IN"], request_key="different-source")
    url = f"/finance/{source['id']}/refund"
    body = refund_body("100.00")
    first = client.post(url, json=body)
    assert first.status_code == 201
    again = client.post(url, json=body)
    assert again.status_code == 200 and again.json() == first.json()
    assert client.post(url, json=body | {"amount": "100.01"}).status_code == 409
    assert client.post(f"/finance/{other['id']}/refund", json=body).status_code == 409
    assert client.post(url, json=body | {"request_key": "source"}).status_code == 409
    assert (
        client.post(
            "/finance", json=operation(concert, categories["IN"], request_key="refund-1")
        ).status_code
        == 409
    )
    assert client.get(f"/concert/{concert}/finance").json()["total"] == 3


def test_voided_refund_releases_remaining_amount(concert_api):
    client, _, data = concert_api
    concert, categories = setup_records(client, data)
    source = register(client, concert, categories["IN"])
    url = f"/finance/{source['id']}"
    body = refund_body("123.45")
    refund = client.post(url + "/refund", json=body).json()
    assert client.post(url + "/void", json={"version": 1, "reason": "Error"}).status_code == 409
    assert (
        client.post(f"/finance/{refund['id']}/refund", json=refund_body("2", "nested")).status_code
        == 409
    )
    voided = client.post(f"/finance/{refund['id']}/void", json={"version": 1, "reason": "Error"})
    assert voided.status_code == 200
    assert client.post(url + "/refund", json=body).json() == voided.json()
    assert client.get(f"/concert/{concert}/finance/totals").json() == {
        "income": "123.45",
        "expenses": "0.00",
        "net": "123.45",
    }
    assert (
        client.post(url + "/refund", json=refund_body("123.45", "replacement")).status_code == 201
    )


def test_refund_validation(concert_api):
    client, _, data = concert_api
    concert, categories = setup_records(client, data)
    source = register(client, concert, categories["IN"])
    draft = client.post("/finance/draft", json=operation(concert, categories["IN"])).json()
    url = f"/finance/{source['id']}/refund"
    for changes in (
        {"occurred_on": "2020-01-31"},
        {"occurred_on": "2999-01-01"},
        {"amount": "0"},
        {"amount": "1.001"},
        {"basis": " "},
        {"request_key": " "},
        {"direction": "OUT"},
        {"contract_id": None},
    ):
        assert client.post(url, json=refund_body("1") | changes).status_code == 422
    assert client.post(f"/finance/{draft['id']}/refund", json=refund_body("1")).status_code == 409
    assert client.post("/finance/999999/refund", json=refund_body("1")).status_code == 404
    assert client.get("/concert/999999/finance/totals").status_code == 404


@pytest.mark.parametrize("same_key", [False, True])
def test_refund_race_over_api(race, same_key):
    engine, data = race

    def override():
        with Session(engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '15s'"))
            yield session

    app.dependency_overrides[get_session] = override
    try:
        with TestClient(app) as client:
            client.auth = ("test_MANAGER", data["password"])
            concert, categories = setup_records(client, data)
            source = register(client, concert, categories["IN"])
            url = f"/finance/{source['id']}/refund"
            bodies = [
                refund_body("80", key) for key in ("first", "first" if same_key else "second")
            ]
            with ThreadPoolExecutor(max_workers=2) as pool:
                with Session(engine) as blocker:
                    FinanceRepository(blocker).get(source["id"], lock=True)
                    futures = [pool.submit(client.post, url, json=body) for body in bodies]
                    deadline = monotonic() + 8
                    while True:
                        with Session(engine) as observer:
                            waiting = observer.scalar(
                                text("""
                                SELECT count(*) FROM pg_stat_activity
                                WHERE datname = current_database() AND wait_event_type = 'Lock'
                                AND (query ILIKE '%FROM finance_entry%FOR UPDATE%'
                                     OR query ILIKE '%SELECT pg_advisory_xact_lock(hashtextextended%')
                            """)
                            )
                        if waiting == 2:
                            break
                        assert monotonic() < deadline, "Both requests must wait on PostgreSQL locks"
                        sleep(0.01)
                    blocker.commit()
                responses = [future.result(timeout=20) for future in futures]
            assert sorted(r.status_code for r in responses) == (
                [200, 201] if same_key else [201, 409]
            )
            if same_key:
                assert responses[0].json() == responses[1].json()
            else:
                assert "43.45" in next(
                    r.json()["detail"] for r in responses if r.status_code == 409
                )
            with Session(engine) as session:
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(FinanceEntry)
                        .where(
                            FinanceEntry.original_id == source["id"],
                        )
                    )
                    == 1
                )
                assert session.get(FinanceEntry, source["id"]).version == 1
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(AuditEvent)
                        .where(
                            AuditEvent.object_type == "finance_entry",
                            AuditEvent.action == "REFUND",
                        )
                    )
                    == 1
                )
    finally:
        app.dependency_overrides.pop(get_session, None)
