import hashlib
import secrets
from time import time

import pytest
from auth_support import LOGIN_HEADER, NO_SESSION, login, session_headers, sign_in
from concert_support import payload
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import COOKIE_NAME, token_digest, verify_password
from app.models.entities import Account, AuditEvent, Concert, Employee
from app.schemas.access import AccountCreate
from app.services.users import UserService


def account_data(login_name="new_manager", password=None, **changes):
    return {
        "login": login_name,
        "password": password or secrets.token_urlsafe(24),
        "full_name": "New employee",
        "position": "Coordinator",
        "roles": ["MANAGER"],
    } | changes


def test_cookie_csrf_revocation_and_login_errors(concert_api):
    client, session, data = concert_api
    login_name, password = "test_MANAGER", data["password"]
    assert (
        client.post("/auth/login", json={"login": login_name, "password": password}).status_code
        == 403
    )
    cross = client.post(
        "/auth/login",
        json={"login": login_name, "password": password},
        headers=LOGIN_HEADER | {"Sec-Fetch-Site": "cross-site"},
    )
    assert cross.status_code == 403
    logins = [login(client, login_name, "wrong"), login(client, "missing", password)]
    assert logins[0].status_code == logins[1].status_code == 401
    assert logins[0].json() == logins[1].json()
    old_cookie = client.cookies[COOKIE_NAME]
    old_csrf = client.headers["X-CSRF-Token"]
    result = sign_in(client, login_name, password)
    flags = result.headers["set-cookie"].lower()
    assert all(flag in flags for flag in ("httponly", "secure", "samesite=lax", "path=/"))
    assert result.headers["cache-control"] == "no-store"
    assert client.cookies[COOKIE_NAME] != old_cookie
    assert (
        client.get("/auth/me", headers={"Cookie": f"{COOKIE_NAME}={old_cookie}"}).status_code == 401
    )
    assert client.get("/auth/me").json() == result.json()
    body = payload(data)
    assert client.post("/concert", json=body, headers=NO_SESSION).status_code == 401
    for headers in (
        {"X-CSRF-Token": ""},
        {"X-CSRF-Token": old_csrf},
        {"Sec-Fetch-Site": "cross-site"},
    ):
        assert client.post("/concert", json=body, headers=headers).status_code == 403
    assert session.scalar(select(func.count()).select_from(Concert)) == 0
    session.commit()
    current = client.cookies[COOKIE_NAME]
    token = current.split(".", 1)[1]
    stored = session.get(Account, data["MANAGER"]["account"]).session_tokens
    assert set(stored) == {token_digest(token)}
    assert token not in str(stored) and result.json()["csrf_token"] not in str(stored)
    session.commit()
    assert client.post("/concert", json=body).status_code == 201
    assert client.post("/auth/logout", headers={"X-CSRF-Token": ""}).status_code == 403
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me", headers={"Cookie": f"{COOKIE_NAME}={current}"}).status_code == 401


def test_expired_session_and_production_cookie_settings(concert_api):
    client, session, data = concert_api
    account = session.get(Account, data["MANAGER"]["account"])
    account.session_tokens = dict.fromkeys(account.session_tokens, int(time()) - 10)
    session.commit()
    assert client.get("/auth/me").status_code == 401
    assert client.post("/concert", json=payload(data)).status_code == 401
    with pytest.raises(ValueError, match="Production requires Secure"):
        Settings(app_env="production", session_cookie_secure=False)
    assert (
        Settings(app_env="test", session_cookie_samesite="strict").session_cookie_samesite
        == "strict"
    )


def test_profile_and_password_change(concert_api):
    client, session, data = concert_api
    login_name, old = "test_MANAGER", data["password"]
    new = secrets.token_urlsafe(24)
    other_session = session_headers(login_name, old)
    current = {
        "Cookie": f"{COOKIE_NAME}={client.cookies[COOKIE_NAME]}",
        "X-CSRF-Token": client.headers["X-CSRF-Token"],
    }
    assert client.get("/auth/profile", headers=NO_SESSION).status_code == 401
    profile = client.get("/auth/profile")
    employee = session.get(Employee, data["MANAGER"]["employee"])
    assert profile.headers["Cache-Control"] == "no-store"
    assert profile.json() == {
        "login": login_name,
        "full_name": employee.full_name,
        "position": employee.position,
        "email": employee.email,
        "phone": employee.phone,
        "roles": ["MANAGER"],
    }
    session.commit()
    path = "/auth/change-password"
    change = {"current_password": old, "new_password": new}
    assert client.post(path, json=change, headers=NO_SESSION).status_code == 401
    assert client.post(path, json=change, headers={"X-CSRF-Token": ""}).status_code == 403
    wrong = client.post(path, json=change | {"current_password": "incorrect"})
    assert wrong.status_code == 400
    assert client.post(path, json=change | {"new_password": old}).status_code == 400
    invalid = client.post(path, json=change | {"new_password": "tiny-secret"})
    assert invalid.status_code == 422
    assert "tiny-secret" not in invalid.text and old not in invalid.text
    assert client.get("/auth/me", headers=other_session).status_code == 200

    changed = client.post(path, json=change)
    assert changed.status_code == 204 and "Max-Age=0" in changed.headers["Set-Cookie"]
    for headers in (current, other_session):
        assert client.get("/auth/me", headers=headers).status_code == 401
    assert login(client, login_name, old).status_code == 401
    account_id = data["MANAGER"]["account"]
    account = session.get(Account, account_id, populate_existing=True)
    assert account.session_tokens == {}
    assert verify_password(new, account.password_hash)
    event = session.scalars(select(AuditEvent).where(AuditEvent.action == "PASSWORD_CHANGE")).one()
    assert event.object_type == "account"
    assert event.object_id == event.actor_id == account_id
    assert event.before_data is None and event.after_data is None and event.reason is None
    session.commit()
    assert login(client, login_name, new).status_code == 200


def test_admin_creates_roles_and_audit_with_no_secrets(concert_api):
    client, session, data = concert_api
    admin = session_headers("test_ADMIN", data["password"])
    original = payload(data)
    assert client.post("/concert", json=original, headers=admin).status_code == 403
    body = account_data(roles=["ADMIN", "MANAGER"])
    assert client.post("/admin/accounts", json=body).status_code == 403
    bad = "SHORT!"
    invalid = client.post("/admin/accounts", json=body | {"password": bad}, headers=admin)
    assert invalid.status_code == 422 and bad not in invalid.text
    created = client.post("/admin/accounts", json=body, headers=admin)
    assert created.status_code == 201, created.text
    account = created.json()
    assert account["roles"] == ["ADMIN", "MANAGER"] and account["active"]
    assert body["password"] not in created.text and "password_hash" not in created.text
    stored = session.get(Account, account["id"]).password_hash
    assert verify_password(body["password"], stored)
    assert stored != body["password"]
    session.commit()
    duplicate = client.post("/admin/accounts", json=body, headers=admin)
    assert duplicate.status_code == 409
    assert session.scalar(select(func.count()).select_from(Employee)) == 3
    session.commit()
    both = session_headers(body["login"], body["password"])
    concert = client.post("/concert", json=original, headers=both)
    assert concert.status_code == 201
    account_path = f"/audit/account/{account['id']}"
    concert_path = f"/audit/concert/{concert.json()['id']}"
    history = client.get(account_path, headers=admin)
    assert history.status_code == 200 and history.json()["total"] == 1
    event = history.json()["items"][0]
    assert event["actor_id"] == data["ADMIN"]["account"]
    assert event["occurred_at"] and event["action"] == "CREATE"
    assert stored not in history.text and body["password"] not in history.text
    assert client.get(account_path).status_code == 403
    assert client.get(concert_path, headers=admin).status_code == 403
    assert client.get(concert_path, headers=both).json()["items"][0]["action"] == "CREATE"
    assert client.get(concert_path, headers=NO_SESSION).status_code == 401
    assert client.get("/audit/concert/9999999").status_code == 404


def test_block_requires_transfer_revokes_sessions_and_audits(concert_api):
    client, session, data = concert_api
    admin = session_headers("test_ADMIN", data["password"])
    replacement = client.post("/admin/accounts", json=account_data(), headers=admin).json()
    ids = [
        client.post("/concert", json=payload(data, shift=shift)).json()["id"] for shift in (0, 1, 2)
    ]
    session.get(Concert, ids[1]).status = "CONFIRMED"
    session.get(Concert, ids[2]).status = "COMPLETED"
    session.commit()
    url = f"/admin/accounts/{data['MANAGER']['account']}/block"
    block = {"version": 1, "reason": "Employment ended"}
    wrong = {"replacement_employee_id": data["ADMIN"]["employee"]}
    assert client.post(url, json=block, headers=admin).status_code == 409
    assert client.post(url, json=block | wrong, headers=admin).status_code == 409
    assert client.get("/auth/me").status_code == 200
    assert client.get(f"/concert/{ids[0]}").json()["responsible_id"] == data["MANAGER"]["employee"]
    transfer = block | {"replacement_employee_id": replacement["employee_id"]}
    assert client.post(url, json=transfer | {"version": 2}, headers=admin).status_code == 409
    result = client.post(url, json=transfer, headers=admin)
    assert result.status_code == 200, result.text
    assert not result.json()["active"] and result.json()["version"] == 2
    assert client.get("/auth/me").status_code == 401
    assert login(client, "test_MANAGER", data["password"]).status_code == 401
    session.expire_all()
    for identity in ids[:2]:
        row = session.get(Concert, identity)
        assert row.responsible_id == replacement["employee_id"] and row.version == 2
        event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.object_type == "concert",
                AuditEvent.object_id == identity,
                AuditEvent.action == "REASSIGN",
            )
        )
        assert event.reason == block["reason"] and event.actor_id == data["ADMIN"]["account"]
        assert event.before_data["responsible_id"] == data["MANAGER"]["employee"]
        assert event.after_data["responsible_id"] == replacement["employee_id"]
    assert session.get(Concert, ids[2]).responsible_id == data["MANAGER"]["employee"]
    assert session.get(Account, data["MANAGER"]["account"]).session_tokens == {}


def test_roles_update_current_session_and_protect_last_admin(concert_api):
    client, _, data = concert_api
    admin = session_headers("test_ADMIN", data["password"])
    url = f"/admin/accounts/{data['MANAGER']['account']}/roles"
    assert (
        client.put(
            url,
            json={"version": 1, "roles": ["MANAGER", "ADMIN"], "reason": "Promotion"},
            headers=admin,
        ).status_code
        == 200
    )
    assert client.get("/auth/me").json()["roles"] == ["ADMIN", "MANAGER"]
    assert client.get("/admin/accounts").status_code == 200
    assert (
        client.put(
            url, json={"version": 2, "roles": ["MANAGER"], "reason": "Transfer"}, headers=admin
        ).status_code
        == 200
    )
    assert client.get("/admin/accounts").status_code == 403
    admin_url = f"/admin/accounts/{data['ADMIN']['account']}/block"
    assert (
        client.post(admin_url, json={"version": 1, "reason": "Leave"}, headers=admin).status_code
        == 409
    )


def test_audit_failure_rolls_back_transfer_block_and_session_revocation(concert_api, monkeypatch):
    client, _, data = concert_api
    admin = session_headers("test_ADMIN", data["password"])
    replacement = client.post("/admin/accounts", json=account_data(), headers=admin).json()
    concert = client.post("/concert", json=payload(data)).json()["id"]
    url = f"/admin/accounts/{data['MANAGER']['account']}/block"
    flush = Session.flush

    def reject(self, *args, **kwargs):
        if any(isinstance(entry, AuditEvent) for entry in self.new):
            raise SQLAlchemyError("audit failure")
        return flush(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "flush", reject)
        with pytest.raises(SQLAlchemyError, match="audit failure"):
            client.post(
                url,
                json={
                    "version": 1,
                    "replacement_employee_id": replacement["employee_id"],
                    "reason": "Transfer",
                },
                headers=admin,
            )
    assert client.get("/auth/me").status_code == 200
    assert client.get(f"/concert/{concert}").json()["responsible_id"] == data["MANAGER"]["employee"]


def test_legacy_password_hash_is_upgraded(concert_api):
    client, session, data = concert_api
    salt = secrets.token_bytes(16)
    password = data["password"]
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    account = session.get(Account, data["MANAGER"]["account"])
    account.password_hash = f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"
    session.commit()
    assert login(client, "test_MANAGER", password).status_code == 200
    session.refresh(account)
    assert account.password_hash.startswith("scrypt$32768$8$3$")
    assert verify_password(password, account.password_hash)


def test_bootstrap_provisions_roles_on_empty_database_once(db):
    conn, _ = db
    outer = conn.begin()
    try:
        with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
            service = UserService(session)
            data = AccountCreate(**account_data(roles=["ADMIN"]))
            result = service.create(data, actor=None)
            assert result.active and result.roles == ["ADMIN"]
            with pytest.raises(HTTPException) as exc:
                service.create(data.model_copy(update={"login": "other_admin"}), actor=None)
            assert exc.value.status_code == 409
            event = session.scalar(select(AuditEvent).where(AuditEvent.object_type == "account"))
            assert event.actor_id == result.id
            assert event.reason == "Initial administrator bootstrap"
    finally:
        outer.rollback()
