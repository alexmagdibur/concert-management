import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.security import hash_password
from app.models.entities import Account, AccountRole, Contract, Counterparty, Employee, Role, Venue

STAMP = datetime(2020, 1, 1, 18, tzinfo=UTC)


def prepare(session):
    technical = {"created_at": STAMP, "updated_at": STAMP, "version": 1}
    password = secrets.token_urlsafe(24)
    data = {"password": password}
    for code in ["MANAGER", "ADMIN"]:
        employee = Employee(full_name=code, position=code, active=True, **technical)
        role = Role(code=code, name=code)
        session.add_all([employee, role])
        session.flush()
        account = Account(
            employee_id=employee.id,
            login=f"test_{code}",
            active=True,
            password_hash=hash_password(password),
        )
        session.add(account)
        session.flush()
        session.add(AccountRole(account_id=account.id, role_id=role.id))
        data[code] = {"employee": employee.id, "account": account.id}
    for i, city in enumerate(["Moscow", "Kazan"], start=1):
        venue = Venue(
            name=f"Hall {i}", city=city, address=f"Street {i}", archived=False, **technical
        )
        party = Counterparty(name=f"Organizer {i}", kind="LEGAL", archived=False, **technical)
        session.add_all([venue, party])
        session.flush()
        data[f"venue{i}"] = venue.id
        data[f"party{i}"] = party.id
    session.flush()
    return data


def payload(data, shift=0, **overrides):
    start = STAMP + timedelta(days=shift)
    return {
        "name": f"Show {shift}",
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=2)).isoformat(),
        "venue_id": data["venue1"],
        "proposed_organizer_id": data["party1"],
        "responsible_id": data["MANAGER"]["employee"],
        "expense_budget": "100000.25",
    } | overrides


def add_contract(session, identity, data, **overrides):
    values = {
        "number": f"MAIN-{identity}",
        "signed_on": STAMP.date(),
        "concert_id": identity,
        "counterparty_id": data["party1"],
        "kind": "MAIN_SHOW",
        "subject": "Show",
        "amount": Decimal("500000.00"),
        "direction": "IN",
        "status": "ACTIVE",
        "created_at": STAMP,
        "updated_at": STAMP,
        "version": 1,
    }
    values.update(overrides)
    contract = Contract(**values)
    session.add(contract)
    session.flush()
    return contract
