import socket
from threading import Thread
from time import monotonic, sleep

import httpx
import pytest
import uvicorn
from auth_support import NO_SESSION, session_headers, sign_in
from concert_support import payload
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.main import app
from app.models.entities import AuditEvent, FinanceEntry


def create_concert(client, data, **changes):
    response = client.post("/concert", json=payload(data, **changes))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_contract(client, concert, party, **changes):
    response = client.post(
        "/contract",
        json={
            "concert_id": concert,
            "counterparty_id": party,
            "number": f"S-{concert}-{party}",
            "kind": "SERVICE",
            "direction": "OUT",
            "subject": "Transport",
            "amount": "123.45",
            "signed_on": "2020-01-01",
        }
        | changes,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def engagement_data(concert, party):
    return {
        "concert_id": concert,
        "counterparty_id": party,
        "description": "Transport",
        "due_at": "2020-02-01T15:00:00+03:00",
        "agreed_amount": "123.45",
    }


def create_engagement(client, concert, party):
    response = client.post("/engagement", json=engagement_data(concert, party))
    assert response.status_code == 201, response.text
    return response.json()


def audit(session, identity):
    return session.scalars(
        select(AuditEvent)
        .where(AuditEvent.object_type == "engagement", AuditEvent.object_id == identity)
        .order_by(AuditEvent.id)
    ).all()


def test_engagement_lifecycle_over_tcp(concert_api, monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        get_settings,
        lambda: Settings(app_env="test", session_cookie_secure=False),
    )
    _, session, data = concert_api
    config = uvicorn.Config(app, loop="asyncio", lifespan="off", log_level="warning")
    server = uvicorn.Server(config)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = monotonic() + 5
            while not server.started and thread.is_alive() and monotonic() < deadline:
                sleep(0.01)
            assert server.started, "Uvicorn did not start"
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}",
                timeout=5,
                trust_env=False,
            ) as client:
                sign_in(client, "test_MANAGER", data["password"])
                concert = create_concert(client, data)
                contract = create_contract(client, concert, data["party2"])
                assert (
                    client.post(f"/contract/{contract}/activate", json={"version": 1}).status_code
                    == 200
                )
                row = create_engagement(client, concert, data["party2"])
                assert row["status"] == "PLANNED" and row["contract_id"] is None
                assert row["due_at"] == "2020-02-01T12:00:00Z"
                root = f"/engagement/{row['id']}"
                result = client.post(root + "/agree", json={"version": 1, "contract_id": contract})
                assert result.status_code == 200, result.text
                assert result.json()["status"] == "AGREED" and result.json()["version"] == 2
                assert client.post(root + "/complete", json={"version": 1}).status_code == 409
                completed = client.post(root + "/complete", json={"version": 2})
                assert completed.status_code == 200, completed.text
                assert completed.json()["status"] == "COMPLETED"
                assert completed.json()["contract_id"] == contract
                assert completed.json()["version"] == 3
                assert client.post(root + "/cancel", json={"version": 3}).status_code == 409
                page = client.get(f"/concert/{concert}/engagement").json()
                assert page["total"] == 1 and page["items"] == [completed.json()]
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive(), "Uvicorn did not stop"

    assert session.scalar(select(func.count()).select_from(FinanceEntry)) == 0
    events = audit(session, row["id"])
    assert [event.action for event in events] == ["CREATE", "AGREE", "COMPLETE"]
    assert events[1].before_data["contract_id"] is None
    assert events[1].after_data["contract_id"] == contract


@pytest.mark.parametrize(
    ("case", "status", "detail"),
    [
        ("concert", 409, "concert_id"),
        ("party", 409, "counterparty_id"),
        ("amount", 409, "amount"),
        ("kind", 409, "service contract"),
        ("missing", 422, "missing contract"),
    ],
)
def test_mismatched_contract_leaves_engagement_unchanged(concert_api, case, status, detail):
    client, session, data = concert_api
    concert = create_concert(client, data)
    party = data["party1"]
    row = create_engagement(client, concert, party)
    contract = 999999
    if case != "missing":
        linked_concert = create_concert(client, data, shift=1) if case == "concert" else concert
        linked_party = data["party2"] if case == "party" else party
        changes = {}
        if case == "amount":
            changes["amount"] = "123.46"
        if case == "kind":
            changes = {"kind": "MAIN_SHOW", "direction": "IN"}
        contract = create_contract(client, linked_concert, linked_party, **changes)
    response = client.post(
        f"/engagement/{row['id']}/agree", json={"version": 1, "contract_id": contract}
    )
    assert response.status_code == status
    assert detail in response.json()["detail"]
    assert client.get(f"/concert/{concert}/engagement").json()["items"] == [row]
    assert [event.action for event in audit(session, row["id"])] == ["CREATE"]


@pytest.mark.parametrize("agreed", [False, True])
def test_cancel_and_terminal_transitions(concert_api, agreed):
    client, session, data = concert_api
    concert = create_concert(client, data)
    party = data["party2"]
    row = create_engagement(client, concert, party)
    contract = create_contract(client, concert, party)
    root = f"/engagement/{row['id']}"
    assert client.post(root + "/complete", json={"version": 1}).status_code == 409
    version = 1
    if agreed:
        assert (
            client.post(root + "/agree", json={"version": 1, "contract_id": contract}).status_code
            == 200
        )
        assert (
            client.post(root + "/agree", json={"version": 2, "contract_id": contract}).status_code
            == 409
        )
        version = 2
    cancelled = client.post(root + "/cancel", json={"version": version, "reason": "Work cancelled"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["contract_id"] == (contract if agreed else None)
    assert audit(session, row["id"])[-1].reason == "Work cancelled"
    for action, extra in (("agree", {"contract_id": contract}), ("cancel", {}), ("complete", {})):
        assert (
            client.post(root + "/" + action, json={"version": version + 1} | extra).status_code
            == 409
        )


def test_contract_link_unique_and_preserved_on_edit(concert_api):
    client, _, data = concert_api
    concert = create_concert(client, data)
    party = data["party2"]
    contract = create_contract(client, concert, party)
    first = create_engagement(client, concert, party)
    second = create_engagement(client, concert, party)
    body = {"version": 1, "contract_id": contract}
    assert client.post(f"/engagement/{first['id']}/agree", json=body).status_code == 200
    response = client.post(f"/engagement/{second['id']}/agree", json=body)
    assert response.status_code == 409 and "already linked" in response.json()["detail"]
    assert client.get(f"/concert/{concert}/engagement", params={"offset": 1}).json()["items"] == [
        second
    ]
    url = f"/contract/{contract}"
    assert client.patch(url, json={"version": 1, "amount": "123.46"}).status_code == 409
    assert (
        client.patch(url, json={"version": 1, "counterparty_id": data["party1"]}).status_code == 409
    )
    assert client.patch(url, json={"version": 1, "subject": "Updated subject"}).status_code == 200


def test_scope_validation_and_permissions(concert_api):
    client, _, data = concert_api
    concert = create_concert(client, data)
    other = create_concert(client, data, shift=1)
    party = data["party2"]
    assert client.get(f"/concert/{other}/engagement").json()["total"] == 0
    row = create_engagement(client, concert, party)
    assert client.get(f"/concert/{other}/engagement").json()["items"] == []
    page = client.get(f"/concert/{concert}/engagement", params={"limit": 1}).json()
    assert page["items"] == [row] and page["total"] == 1
    body = engagement_data(concert, party)
    for bad in (
        {"concert_id": 999999},
        {"counterparty_id": 999999},
        {"description": " "},
        {"agreed_amount": "0"},
        {"agreed_amount": "1.001"},
        {"due_at": "2020-02-01T15:00:00"},
        {"contract_id": 1},
        {"status": "AGREED"},
    ):
        assert client.post("/engagement", json=body | bad).status_code == 422
    assert client.get("/concert/999999/engagement").status_code == 404
    assert client.post("/engagement/999999/complete", json={"version": 1}).status_code == 404
    assert client.post("/engagement", json=body, headers=NO_SESSION).status_code == 401
    assert (
        client.post(
            "/engagement", json=body, headers=session_headers("test_ADMIN", data["password"])
        ).status_code
        == 403
    )
