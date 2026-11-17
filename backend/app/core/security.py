"""HTTP Basic adapter; session authentication is a separate feature."""

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models.entities import Account, AccountRole, Employee, Role

basic = HTTPBasic()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if (algorithm, n, r, p) != ("scrypt", "16384", "8", "1"):
            return False
        salt_bytes, expected_bytes = bytes.fromhex(salt), bytes.fromhex(expected)
        if len(salt_bytes) != 16 or len(expected_bytes) != 64:
            return False
        actual = hashlib.scrypt(password.encode(), salt=salt_bytes, n=16384, r=8, p=1)
        return secrets.compare_digest(actual, expected_bytes)
    except ValueError, TypeError:
        return False


# Unknown users still execute the same password hashing work.
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def require_manager(
    credentials: Annotated[HTTPBasicCredentials, Depends(basic)],
    session: Annotated[Session, Depends(get_session)],
) -> Account:
    account = session.scalar(select(Account).where(Account.login == credentials.username))
    valid = verify_password(credentials.password, account.password_hash if account else DUMMY_HASH)
    employee = session.get(Employee, account.employee_id) if account else None
    if (
        not valid
        or account is None
        or not account.active
        or employee is None
        or not employee.active
    ):
        raise HTTPException(
            401, "Invalid credentials or inactive account", headers={"WWW-Authenticate": "Basic"}
        )
    manager = session.scalar(
        select(Role.id)
        .join(AccountRole, AccountRole.role_id == Role.id)
        .where(AccountRole.account_id == account.id, Role.code == "MANAGER")
    )
    if manager is None:
        raise HTTPException(403, "MANAGER role required")
    return account
