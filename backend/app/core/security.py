"""Opaque revocable sessions, role checks and synchronizer CSRF tokens."""

import hashlib
import re
import secrets
from dataclasses import dataclass
from time import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models.entities import Account
from app.repositories.account import AccountRepository

COOKIE_NAME = "concert_session"
COOKIE = APIKeyCookie(name=COOKIE_NAME, auto_error=False)
TOKEN_PATTERN = re.compile(r"(-?[0-9]{1,19})\.([A-Za-z0-9_-]{43})")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PASSWORD_PARAMS = (32768, 8, 3)
LEGACY_PARAMS = (16384, 8, 1)


def _scrypt(password: str, salt: bytes, params: tuple[int, int, int]) -> bytes:
    n, r, p = params
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=64 * 1024**2)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, PASSWORD_PARAMS)
    return f"scrypt$32768$8$3${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        params = int(n), int(r), int(p)
        if algorithm != "scrypt" or params not in {PASSWORD_PARAMS, LEGACY_PARAMS}:
            return False
        salt_bytes, expected_bytes = bytes.fromhex(salt), bytes.fromhex(expected)
        if len(salt_bytes) != 16 or len(expected_bytes) != 64:
            return False
        return secrets.compare_digest(_scrypt(password, salt_bytes, params), expected_bytes)
    except ValueError, TypeError:
        return False


DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def csrf_token(token: str) -> str:
    return hashlib.sha256(f"concert-crm:csrf:{token}".encode("ascii")).hexdigest()


@dataclass(frozen=True)
class Identity:
    account: Account
    roles: list[str]
    token: str


def require_identity(
    request: Request,
    cookie: Annotated[str | None, Depends(COOKIE)],
    session: Annotated[Session, Depends(get_session)],
) -> Identity:
    match = TOKEN_PATTERN.fullmatch(cookie or "")
    if match is None:
        raise HTTPException(401, "Authentication required")
    account_id = int(match[1])
    if not -(2**63) <= account_id < 2**63:
        raise HTTPException(401, "Authentication required")
    repo = AccountRepository(session)
    account = repo.get(account_id)
    token = match[2]
    if (
        account is None
        or not account.active
        or account.session_tokens.get(token_digest(token), 0) <= time()
        or not repo.employee_active(account)
    ):
        raise HTTPException(401, "Authentication required")
    if request.method not in SAFE_METHODS:
        provided = request.headers.get("X-CSRF-Token", "")
        if (
            request.headers.get("Sec-Fetch-Site") == "cross-site"
            or not provided.isascii()
            or not secrets.compare_digest(provided, csrf_token(token))
        ):
            raise HTTPException(403, "Invalid CSRF token")
    return Identity(account=account, roles=repo.roles(account.id), token=token)


def require_manager(identity: Annotated[Identity, Depends(require_identity)]) -> Account:
    if "MANAGER" not in identity.roles:
        raise HTTPException(403, "MANAGER role required")
    return identity.account


def require_admin(identity: Annotated[Identity, Depends(require_identity)]) -> Account:
    if "ADMIN" not in identity.roles:
        raise HTTPException(403, "ADMIN role required")
    return identity.account
