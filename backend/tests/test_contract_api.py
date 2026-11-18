from decimal import Decimal

import pytest
from concert_support import STAMP, payload
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.entities import AuditEvent, Contract, FinanceCategory, FinanceEntry


def create_concert(client, data, **changes):
    result = client.post("/concert", json=payload(data, **changes))
    assert result.status_code == 201, result.text
    return result.json()["id"]


def draft_data(identity, data, **changes):
    return {
        "concert_id": identity,
        "counterparty_id": data["party1"],
        "number": "SHOW-01",
        "kind": "MAIN_SHOW",
        "signed_on": "2020-01-01",
        "subject": "Artist performance",
        "direction": "IN",
        "amount": "500000.00",
    } | changes


def create_contract(client, values):
    result = client.post("/contract", json=values)
    assert result.status_code == 201, result.text
    return result.json()


def test_concert_contract_workflow(concert_api):
    client, session, data = concert_api
    concert_id = create_concert(client, data)
    draft = create_contract(client, draft_data(concert_id, data))
    url = f"/contract/{draft['id']}"
    assert draft["status"] == "DRAFT" and draft["version"] == 1
    assert client.get(url).json() == draft
    confirm = f"/concert/{concert_id}/confirm"
    assert client.post(confirm, json={"version": 1}).status_code == 409
    patch = client.patch(url, json={"version": 1, "amount": "450000.25", "number": "SHOW-02"})
    assert patch.status_code == 200
    assert patch.json()["version"] == 2 and patch.json()["amount"] == "450000.25"
    assert client.post(url + "/activate", json={"version": 1}).status_code == 409
    active = client.post(url + "/activate", json={"version": 2})
    assert active.status_code == 200 and active.json()["status"] == "ACTIVE"
    assert active.json()["version"] == 3
    assert client.patch(url, json={"version": 3, "subject": "Changed"}).status_code == 409
    assert client.post(url + "/activate", json={"version": 3}).status_code == 409
    result = client.post(confirm, json={"version": 1})
    assert result.status_code == 200 and result.json()["status"] == "CONFIRMED"
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.object_type == "contract").order_by(AuditEvent.id)
    ).all()
    assert [e.action for e in events] == ["CREATE", "UPDATE", "ACTIVATE"]
    assert events[-1].before_data["status"] == "DRAFT"
    assert events[-1].after_data["status"] == "ACTIVE"


def test_search_service_and_financial_reference(concert_api):
    client, session, data = concert_api
    identity = create_concert(client, data)
    values = draft_data(
        identity,
        data,
        kind="SERVICE",
        direction="OUT",
        counterparty_id=data["party2"],
        number="Service-%_1",
    )
    service = create_contract(client, values)
    create_contract(client, draft_data(identity, data, number="Service-XX1"))
    endpoint = f"/contract/{service['id']}"
    assert client.post(endpoint + "/activate", json={"version": 1}).status_code == 200
    assert client.post(f"/concert/{identity}/confirm", json={"version": 1}).status_code == 409
    filters = {"number": "SERVICE-", "counterparty": "organizer 2", "concert_id": identity}
    page = client.get("/contract", params=filters).json()
    assert page["total"] == 1 and page["items"][0]["id"] == service["id"]
    assert client.get("/contract", params={"number": "%_"}).json()["total"] == 1
    assert client.get("/contract", params={"limit": 1, "offset": 1}).json()["total"] == 2
    timestamps = {"created_at": STAMP, "updated_at": STAMP, "version": 1}
    category = FinanceCategory(
        code="COST", name="Cost", normal_direction="OUT", archived=False, **timestamps
    )
    session.add(category)
    session.flush()
    session.add(
        FinanceEntry(
            concert_id=identity,
            contract_id=service["id"],
            category_id=category.id,
            occurred_on=STAMP.date(),
            amount=Decimal("20.00"),
            direction="OUT",
            basis="Contractor cost",
            status="POSTED",
            posted_at=STAMP,
            request_key="contract-cost",
            created_by=data["MANAGER"]["account"],
            **timestamps,
        )
    )
    session.commit()
    assert client.delete(endpoint).status_code == 405
    with pytest.raises(IntegrityError) as exc, session.begin_nested():
        session.delete(session.get(Contract, service["id"]))
        session.flush()
    assert exc.value.orig.diag.constraint_name == "finance_entry_contract_id_fkey"
    assert session.scalar(select(FinanceEntry.contract_id)) == service["id"]


def test_duplicate_identity_and_activation_conflicts(concert_api):
    client, _, data = concert_api
    identity = create_concert(client, data)
    original = draft_data(identity, data)
    first = create_contract(client, original)
    assert client.post("/contract", json=original).status_code == 409
    second = create_contract(client, original | {"number": "SHOW-02"})
    endpoint = f"/contract/{second['id']}"
    assert client.patch(endpoint, json={"version": 1, "number": first["number"]}).status_code == 409
    assert client.post(f"/contract/{first['id']}/activate", json={"version": 1}).status_code == 200
    assert client.post(endpoint + "/activate", json={"version": 1}).status_code == 409
    assert client.get(endpoint).json() == second


def test_activation_rechecks_changed_organizer(concert_api):
    client, _, data = concert_api
    identity = create_concert(client, data)
    draft = create_contract(client, draft_data(identity, data))
    result = client.patch(
        f"/concert/{identity}", json={"version": 1, "proposed_organizer_id": data["party2"]}
    )
    assert result.status_code == 200
    endpoint = f"/contract/{draft['id']}"
    assert client.post(endpoint + "/activate", json={"version": 1}).status_code == 409
    assert client.get(endpoint).json() == draft


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"number": " "}, 422),
        ({"number": "x" * 81}, 422),
        ({"subject": " "}, 422),
        ({"signed_on": "2020-02-30"}, 422),
        ({"signed_on": "1609459200"}, 422),
        ({"signed_on": "2020-01-01T00:00:00"}, 422),
        ({"amount": "0"}, 422),
        ({"amount": "1.001"}, 422),
        ({"amount": "1000000000000"}, 422),
        ({"direction": "OUT"}, 422),
        ({"kind": "SERVICE"}, 422),
        ({"kind": "UNKNOWN"}, 422),
        ({"concert_id": 999999}, 422),
        ({"counterparty_id": 999999}, 422),
        ({"status": "ACTIVE"}, 422),
    ],
)
def test_invalid_contract_create(concert_api, changes, expected):
    client, _, data = concert_api
    identity = create_concert(client, data)
    assert (
        client.post("/contract", json=draft_data(identity, data, **changes)).status_code == expected
    )
    assert client.get("/contract").json()["total"] == 0


def test_references_access_and_invalid_patches(concert_api):
    client, _, data = concert_api
    identity = create_concert(client, data)
    values = draft_data(identity, data)
    assert (
        client.post("/contract", json=values | {"counterparty_id": data["party2"]}).status_code
        == 409
    )
    draft = create_contract(client, values)
    assert (
        client.post(f"/counterparty/{data['party2']}/archive", json={"version": 1}).status_code
        == 200
    )
    assert (
        client.post(
            "/contract",
            json=values
            | {"kind": "SERVICE", "direction": "OUT", "counterparty_id": data["party2"]},
        ).status_code
        == 409
    )
    endpoint = f"/contract/{draft['id']}"
    for changes in [{"subject": None}, {"concert_id": identity}, {"direction": "OUT"}, {}]:
        assert client.patch(endpoint, json={"version": 1} | changes).status_code == 422
    assert client.get(endpoint).json() == draft
    assert client.get("/contract/999999").status_code == 404
    assert client.get("/contract", auth=None).status_code == 401
    assert client.get("/contract", auth=("test_ADMIN", data["password"])).status_code == 403
