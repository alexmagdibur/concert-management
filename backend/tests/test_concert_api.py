from datetime import timedelta
from decimal import Decimal

import pytest
from concert_support import STAMP, add_contract, payload
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

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


def create(client, data, **values):
    response = client.post("/concert", json=payload(data, **values))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_read_edit_and_controlled_response(concert_api):
    client, session, data = concert_api
    row = create(client, data, venue_id=None, proposed_organizer_id=None)
    assert row["status"] == "NEGOTIATING" and row["version"] == 1
    assert row["venue_id"] is None and row["cancel_reason"] is None
    assert row["expense_budget"] == "100000.25"
    assert set(row) == {column.name for column in Concert.__table__.columns}
    assert client.get(f"/concert/{row['id']}").json() == row
    edited = client.patch(
        f"/concert/{row['id']}",
        json={
            "version": 1,
            "name": "New",
            "starts_at": (STAMP + timedelta(days=2)).isoformat(),
            "ends_at": (STAMP + timedelta(days=2, hours=3)).isoformat(),
            "venue_id": data["venue2"],
            "proposed_organizer_id": data["party2"],
            "responsible_id": data["MANAGER"]["employee"],
            "expense_budget": "999999999999.99",
        },
    )
    assert edited.status_code == 200, edited.text
    updated = edited.json()
    assert updated["version"] == 2 and updated["name"] == "New"
    assert updated["venue_id"] == data["venue2"]
    assert updated["proposed_organizer_id"] == data["party2"]
    assert session.get(Concert, row["id"]).expense_budget == Decimal("999999999999.99")
    cleared = client.patch(
        f"/concert/{row['id']}",
        json={"version": 2, "venue_id": None, "proposed_organizer_id": None},
    )
    assert cleared.status_code == 200 and cleared.json()["venue_id"] is None
    assert client.delete(f"/concert/{row['id']}").status_code == 405


@pytest.mark.parametrize(
    "source,action,target",
    [
        ("NEGOTIATING", "confirm", "CONFIRMED"),
        ("NEGOTIATING", "cancel", "CANCELLED"),
        ("CONFIRMED", "complete", "COMPLETED"),
        ("CONFIRMED", "cancel", "CANCELLED"),
    ],
)
def test_successful_transitions(concert_api, source, action, target):
    client, session, data = concert_api
    row = create(client, data)
    entity = session.get(Concert, row["id"])
    entity.status = source
    add_contract(session, row["id"], data)
    session.commit()
    body = {"version": 1}
    if action == "cancel":
        body["reason"] = "Organizer cancelled"
    response = client.post(f"/concert/{row['id']}/{action}", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == target and response.json()["version"] == 2
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == target))
    assert event.actor_id == data["MANAGER"]["account"]
    assert event.before_data["status"] == source and event.after_data["status"] == target
    if action == "cancel":
        assert event.reason == body["reason"] == response.json()["cancel_reason"]


@pytest.mark.parametrize(
    "source,action",
    [
        ("NEGOTIATING", "complete"),
        ("CONFIRMED", "confirm"),
        ("COMPLETED", "confirm"),
        ("COMPLETED", "complete"),
        ("COMPLETED", "cancel"),
        ("CANCELLED", "confirm"),
        ("CANCELLED", "complete"),
        ("CANCELLED", "cancel"),
    ],
)
def test_invalid_transitions_are_atomic(concert_api, source, action):
    client, session, data = concert_api
    row = create(client, data)
    session.get(Concert, row["id"]).status = source
    session.commit()
    body = {"version": 1, **({"reason": "Reason"} if action == "cancel" else {})}
    response = client.post(f"/concert/{row['id']}/{action}", json=body)
    assert response.status_code == 409
    current = client.get(f"/concert/{row['id']}").json()
    assert current["status"] == source and current["version"] == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "draft",
        "closed",
        "service",
        "other_concert",
        "wrong_organizer",
        "no_organizer",
        "wrong_direction",
        "no_venue",
        "inactive_employee",
        "inactive_account",
    ],
)
def test_confirmation_requires_real_prerequisites(concert_api, problem):
    client, session, data = concert_api
    row = create(
        client,
        data,
        **({"venue_id": None} if problem == "no_venue" else {}),
        **({"proposed_organizer_id": None} if problem == "no_organizer" else {}),
    )
    if problem != "missing":
        changes = {}
        if problem in {"draft", "closed"}:
            changes["status"] = problem.upper()
        if problem == "service":
            changes["kind"] = "SERVICE"
        if problem == "wrong_organizer":
            changes["counterparty_id"] = data["party2"]
        if problem == "wrong_direction":
            changes["direction"] = "OUT"
        identity = row["id"]
        if problem == "other_concert":
            identity = create(client, data, shift=2)["id"]
        add_contract(session, identity, data, **changes)
    if problem == "inactive_employee":
        session.get(Employee, data["MANAGER"]["employee"]).active = False
        # Another active manager makes the request, avoiding authentication failure.
        session.get(Account, data["ADMIN"]["account"]).active = True
        manager_role = session.scalar(select(Role).where(Role.code == "MANAGER"))
        session.add(AccountRole(account_id=data["ADMIN"]["account"], role_id=manager_role.id))
        client.auth = ("test_ADMIN", data["password"])
    if problem == "inactive_account":
        session.get(Account, data["MANAGER"]["account"]).active = False
        manager_role = session.scalar(select(Role).where(Role.code == "MANAGER"))
        session.add(AccountRole(account_id=data["ADMIN"]["account"], role_id=manager_role.id))
        client.auth = ("test_ADMIN", data["password"])
    session.commit()
    response = client.post(f"/concert/{row['id']}/confirm", json={"version": 1})
    assert response.status_code == 409, response.text
    current = client.get(f"/concert/{row['id']}").json()
    assert current["status"] == "NEGOTIATING" and current["version"] == 1


@pytest.mark.parametrize(
    "delta_start,delta_end,expected",
    [
        (-1, 1, 409),
        (0, 2, 409),
        (1, 3, 409),
        (-1, 3, 409),
        (0.5, 1.5, 409),
        (-2, 0, 200),
        (2, 4, 200),
    ],
)
def test_schedule_overlap_and_adjacency(concert_api, delta_start, delta_end, expected):
    client, session, data = concert_api
    first = create(client, data)
    second = create(
        client,
        data,
        starts_at=(STAMP + timedelta(hours=delta_start)).isoformat(),
        ends_at=(STAMP + timedelta(hours=delta_end)).isoformat(),
    )
    add_contract(session, first["id"], data)
    add_contract(session, second["id"], data)
    session.commit()
    assert client.post(f"/concert/{first['id']}/confirm", json={"version": 1}).status_code == 200
    response = client.post(f"/concert/{second['id']}/confirm", json={"version": 1})
    assert response.status_code == expected, response.text


def test_confirmed_edit_rechecks_schedule_contract_and_venue(concert_api):
    client, session, data = concert_api
    first = create(client, data)
    second = create(client, data, shift=2)
    for row in [first, second]:
        add_contract(session, row["id"], data)
    session.commit()
    for row in [first, second]:
        assert client.post(f"/concert/{row['id']}/confirm", json={"version": 1}).status_code == 200
    for changes in [
        {"venue_id": None},
        {"proposed_organizer_id": data["party2"]},
        {"starts_at": first["starts_at"], "ends_at": first["ends_at"]},
    ]:
        response = client.patch(f"/concert/{second['id']}", json={"version": 2, **changes})
        assert response.status_code == 409
    current = client.get(f"/concert/{second['id']}").json()
    assert current["version"] == 2 and current["starts_at"] == second["starts_at"]
    assert (
        client.patch(f"/concert/{second['id']}", json={"version": 2, "name": "Changed"}).status_code
        == 200
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", " "),
        ("name", "x" * 201),
        ("expense_budget", "-0.01"),
        ("expense_budget", "0.001"),
        ("expense_budget", "1000000000000.00"),
        ("expense_budget", "NaN"),
        ("expense_budget", "Infinity"),
        ("starts_at", "2020-01-01T18:00:00"),
        ("ends_at", "2020-01-01T17:00:00Z"),
        ("status", "CONFIRMED"),
        ("responsible_id", None),
    ],
)
def test_create_validation(concert_api, field, value):
    client, session, data = concert_api
    assert client.post("/concert", json=payload(data, **{field: value})).status_code == 422
    assert session.scalar(select(func.count()).select_from(Concert)) == 0


@pytest.mark.parametrize("field", ["venue_id", "proposed_organizer_id", "responsible_id"])
def test_missing_references_rejected(concert_api, field):
    client, _, data = concert_api
    assert client.post("/concert", json=payload(data, **{field: 999999999})).status_code == 422
    row = create(client, data)
    assert (
        client.patch(f"/concert/{row['id']}", json={"version": 1, field: 999999999}).status_code
        == 422
    )


def test_archived_new_choices_and_responsible_role(concert_api):
    client, session, data = concert_api
    session.get(Venue, data["venue1"]).archived = True
    session.commit()
    assert client.post("/concert", json=payload(data)).status_code == 409
    assert (
        client.post(
            "/concert", json=payload(data, venue_id=None, responsible_id=data["ADMIN"]["employee"])
        ).status_code
        == 409
    )
    row = create(client, data, venue_id=None)
    assert (
        client.patch(
            f"/concert/{row['id']}", json={"version": 1, "venue_id": data["venue1"]}
        ).status_code
        == 409
    )


def test_version_and_partial_update_validation(concert_api):
    client, _session, data = concert_api
    row = create(client, data)
    assert (
        client.patch(f"/concert/{row['id']}", json={"version": 1, "name": "New"}).status_code == 200
    )
    for action in ["confirm", "complete", "cancel"]:
        body = {"version": 1, **({"reason": "Reason"} if action == "cancel" else {})}
        assert client.post(f"/concert/{row['id']}/{action}", json=body).status_code == 409
    assert (
        client.patch(f"/concert/{row['id']}", json={"version": 1, "name": "Lost"}).status_code
        == 409
    )
    for body in [
        {"version": 2},
        {"name": "No version"},
        {"version": 2, "name": None},
        {"version": 2, "starts_at": None},
        {"version": 2, "status": "COMPLETED"},
        {"version": 2, "starts_at": (STAMP + timedelta(days=5)).isoformat()},
    ]:
        assert client.patch(f"/concert/{row['id']}", json=body).status_code == 422
    for reason in [None, "", "   "]:
        assert (
            client.post(
                f"/concert/{row['id']}/cancel", json={"version": 2, "reason": reason}
            ).status_code
            == 422
        )
    assert client.get(f"/concert/{row['id']}").json()["version"] == 2


def test_cancellation_keeps_contracts_finance_and_audit(concert_api):
    client, session, data = concert_api
    row = create(client, data)
    contract = add_contract(session, row["id"], data)
    category = FinanceCategory(
        code="FEE",
        name="Fee",
        normal_direction="IN",
        archived=False,
        created_at=STAMP,
        updated_at=STAMP,
        version=1,
    )
    session.add(category)
    session.flush()
    entry = FinanceEntry(
        concert_id=row["id"],
        contract_id=contract.id,
        category_id=category.id,
        occurred_on=STAMP.date(),
        amount=Decimal("25.00"),
        direction="IN",
        basis="Paper",
        status="POSTED",
        created_by=data["MANAGER"]["account"],
        request_key="cancel-test",
        posted_at=STAMP,
        created_at=STAMP,
        updated_at=STAMP,
        version=1,
    )
    session.add(entry)
    session.commit()
    assert client.post(f"/concert/{row['id']}/confirm", json={"version": 1}).status_code == 200
    result = client.post(
        f"/concert/{row['id']}/cancel", json={"version": 2, "reason": "Cancelled by organizer"}
    )
    assert result.status_code == 200 and result.json()["version"] == 3
    session.expire_all()
    assert session.get(Contract, contract.id).status == "ACTIVE"
    assert session.get(FinanceEntry, entry.id).status == "POSTED"
    assert session.get(FinanceEntry, entry.id).amount == Decimal("25.00")
    events = session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
    assert [event.action for event in events] == ["CREATE", "CONFIRMED", "CANCELLED"]


def test_complete_only_after_end(concert_api):
    client, session, data = concert_api
    row = create(client, data, starts_at="2999-01-01T18:00:00Z", ends_at="2999-01-01T20:00:00Z")
    add_contract(session, row["id"], data)
    session.commit()
    assert client.post(f"/concert/{row['id']}/confirm", json={"version": 1}).status_code == 200
    assert client.post(f"/concert/{row['id']}/complete", json={"version": 2}).status_code == 409


def test_search_period_city_pagination_and_authorization(concert_api):
    client, _, data = concert_api
    rows = [
        create(client, data, shift=i, venue_id=(data["venue1"] if i < 2 else data["venue2"]))
        for i in range(3)
    ]
    create(client, data, shift=4, venue_id=None)
    parameters = {
        "starts_from": (STAMP + timedelta(days=1)).isoformat(),
        "starts_before": (STAMP + timedelta(days=3)).isoformat(),
        "city": "MOSCOW",
    }
    page = client.get("/concert", params=parameters)
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1 and page.json()["items"][0]["id"] == rows[1]["id"]
    assert client.get("/concert").json()["total"] == 4
    assert client.get("/concert", params={"city": "%' OR 1=1 --"}).json()["total"] == 0
    assert (
        client.get("/concert", params={"limit": 1, "offset": 1}).json()["items"][0]["id"]
        == rows[1]["id"]
    )
    for parameters in [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"city": " "},
        {"starts_from": "2020-01-01T00:00:00"},
        {"starts_from": rows[1]["starts_at"], "starts_before": rows[0]["starts_at"]},
    ]:
        assert client.get("/concert", params=parameters).status_code == 422
    assert client.get("/concert/999999999").status_code == 404
    assert (
        client.patch("/concert/999999999", json={"version": 1, "name": "Missing"}).status_code
        == 404
    )
    assert client.post("/concert/999999999/confirm", json={"version": 1}).status_code == 404
    assert client.get("/concert", auth=None).status_code == 401
    assert client.get("/concert", auth=("test_ADMIN", data["password"])).status_code == 403


def test_transition_audit_failure_rolls_back_state(concert_api, monkeypatch):
    client, session, data = concert_api
    row = create(client, data)
    add_contract(session, row["id"], data)
    session.commit()
    original = Session.flush

    def fail_audit(self, *args, **kwargs):
        if any(isinstance(event, AuditEvent) for event in self.new):
            raise SQLAlchemyError("Simulated audit failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Session, "flush", fail_audit)
    with pytest.raises(SQLAlchemyError):
        client.post(f"/concert/{row['id']}/confirm", json={"version": 1})
    monkeypatch.setattr(Session, "flush", original)
    current = client.get(f"/concert/{row['id']}").json()
    assert current["status"] == "NEGOTIATING" and current["version"] == 1
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_only_confirmed_concerts_block_and_cancel_frees_time(concert_api):
    client, session, data = concert_api
    first = create(client, data)
    second = create(client, data)
    for row in [first, second]:
        add_contract(session, row["id"], data)
    session.commit()
    assert client.post(f"/concert/{first['id']}/confirm", json={"version": 1}).status_code == 200
    assert client.post(f"/concert/{second['id']}/confirm", json={"version": 1}).status_code == 409
    assert (
        client.post(
            f"/concert/{first['id']}/cancel", json={"version": 2, "reason": "Cancelled"}
        ).status_code
        == 200
    )
    assert client.post(f"/concert/{second['id']}/confirm", json={"version": 1}).status_code == 200
    assert (
        client.get("/concert", params={"status": "CANCELLED"}).json()["items"][0]["id"]
        == first["id"]
    )


def test_archived_organizer_not_available_for_new_assignment(concert_api):
    client, session, data = concert_api
    session.get(Counterparty, data["party1"]).archived = True
    session.commit()
    assert client.post("/concert", json=payload(data)).status_code == 409
    row = create(client, data, proposed_organizer_id=None)
    assert (
        client.patch(
            f"/concert/{row['id']}", json={"version": 1, "proposed_organizer_id": data["party1"]}
        ).status_code
        == 409
    )


def test_city_search_is_unicode_and_historical_venue_stays_linked(concert_api):
    client, session, data = concert_api
    city = "\u041c\u043e\u0441\u043a\u0432\u0430"
    session.get(Venue, data["venue1"]).city = city
    session.commit()
    row = create(client, data)
    session.get(Venue, data["venue1"]).archived = True
    session.commit()
    result = client.get("/concert", params={"city": city.upper()})
    assert result.status_code == 200 and result.json()["items"][0]["id"] == row["id"]
    # Editing unrelated fields preserves the existing archived reference.
    assert (
        client.patch(f"/concert/{row['id']}", json={"version": 1, "name": "Corrected"}).status_code
        == 200
    )


@pytest.mark.parametrize("final_state", ["COMPLETED", "CANCELLED"])
def test_final_card_corrections_keep_state_contract_and_version_audit(concert_api, final_state):
    client, session, data = concert_api
    row = create(client, data)
    contract = add_contract(session, row["id"], data)
    session.commit()
    assert client.post(f"/concert/{row['id']}/confirm", json={"version": 1}).status_code == 200
    action = "complete" if final_state == "COMPLETED" else "cancel"
    body = {"version": 2, **({"reason": "Reason"} if action == "cancel" else {})}
    assert client.post(f"/concert/{row['id']}/{action}", json=body).status_code == 200
    corrected = client.patch(
        f"/concert/{row['id']}",
        json={"version": 3, "name": "Correction", "expense_budget": "123.45"},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["version"] == 4 and corrected.json()["status"] == final_state
    assert corrected.json()["cancel_reason"] == ("Reason" if final_state == "CANCELLED" else None)
    session.expire_all()
    assert session.get(Contract, contract.id).amount == Decimal("500000.00")
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "UPDATE"))
    assert event.before_data["name"] == row["name"] and event.after_data["name"] == "Correction"
    assert event.before_data["status"] == event.after_data["status"] == final_state
    assert (
        client.patch(f"/concert/{row['id']}", json={"version": 3, "name": "Lost"}).status_code
        == 409
    )
    assert (
        client.patch(
            f"/concert/{row['id']}", json={"version": 4, "proposed_organizer_id": data["party2"]}
        ).status_code
        == 409
    )
    if final_state == "COMPLETED":
        assert (
            client.patch(f"/concert/{row['id']}", json={"version": 4, "venue_id": None}).status_code
            == 409
        )
        assert (
            client.patch(
                f"/concert/{row['id']}",
                json={
                    "version": 4,
                    "starts_at": "2999-01-01T18:00:00Z",
                    "ends_at": "2999-01-01T20:00:00Z",
                },
            ).status_code
            == 409
        )


def test_reassign_to_another_real_active_manager(concert_api):
    client, session, data = concert_api
    manager_role = session.scalar(select(Role).where(Role.code == "MANAGER"))
    session.add(AccountRole(account_id=data["ADMIN"]["account"], role_id=manager_role.id))
    session.commit()
    row = create(client, data)
    result = client.patch(
        f"/concert/{row['id']}", json={"version": 1, "responsible_id": data["ADMIN"]["employee"]}
    )
    assert (
        result.status_code == 200 and result.json()["responsible_id"] == data["ADMIN"]["employee"]
    )


def test_completed_correction_does_not_require_reactivating_closed_contract(concert_api):
    client, session, data = concert_api
    row = create(client, data)
    contract = add_contract(session, row["id"], data)
    session.commit()
    assert client.post(f"/concert/{row['id']}/confirm", json={"version": 1}).status_code == 200
    assert client.post(f"/concert/{row['id']}/complete", json={"version": 2}).status_code == 200
    contract.status = "CLOSED"
    session.commit()
    corrected = client.patch(
        f"/concert/{row['id']}", json={"version": 3, "name": "Corrected history"}
    )
    assert corrected.status_code == 200 and corrected.json()["status"] == "COMPLETED"
    session.expire_all()
    assert session.get(Contract, contract.id).status == "CLOSED"


def test_zero_budget_round_trip_is_decimal_and_consistent(concert_api):
    client, session, data = concert_api
    row = create(client, data, expense_budget="0")
    assert row["expense_budget"] == "0.00"
    assert client.get(f"/concert/{row['id']}").json() == row
    assert session.get(Concert, row["id"]).expense_budget == Decimal("0.00")
