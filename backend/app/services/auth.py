import secrets
from time import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import (
    DUMMY_HASH,
    Identity,
    csrf_token,
    hash_password,
    token_digest,
    verify_password,
)
from app.repositories.account import AccountRepository
from app.schemas.access import Credentials, SessionResponse


class AuthService:
    def __init__(self, session: Session):
        self.session = session
        self.accounts = AccountRepository(session)

    @staticmethod
    def describe(identity: Identity) -> SessionResponse:
        return SessionResponse(
            account_id=identity.account.id,
            login=identity.account.login,
            roles=identity.roles,
            csrf_token=csrf_token(identity.token),
        )

    def login(self, data: Credentials, settings: Settings, previous_cookie: str | None):
        account = self.accounts.by_login(data.login)
        encoded = account.password_hash if account is not None else DUMMY_HASH
        password = data.password.get_secret_value()
        if not verify_password(password, encoded) or account is None:
            raise HTTPException(401, "Invalid credentials or inactive account")

        account = self.accounts.get(account.id, lock=True)
        if (
            account is None
            or not account.active
            or account.password_hash != encoded
            or not self.accounts.employee_active(account)
        ):
            raise HTTPException(401, "Invalid credentials or inactive account")
        if encoded.startswith("scrypt$16384$8$1$"):
            account.password_hash = hash_password(password)

        token = secrets.token_urlsafe(32)
        now = int(time())
        stored = {key: expiry for key, expiry in account.session_tokens.items() if expiry > now}
        # Rotate the browser's previous session for this account, if present.
        if previous_cookie and previous_cookie.startswith(f"{account.id}."):
            previous = previous_cookie.split(".", 1)[1]
            if previous.isascii():
                stored.pop(token_digest(previous), None)
        active = dict(sorted(stored.items(), key=lambda item: item[1])[-9:])
        active[token_digest(token)] = now + settings.session_ttl_seconds
        account.session_tokens = active
        result = self.describe(Identity(account, self.accounts.roles(account.id), token))
        self.session.commit()
        return result, f"{result.account_id}.{token}"

    def logout(self, identity: Identity) -> None:
        account = self.accounts.get(identity.account.id, lock=True)
        if account is not None:
            active = dict(account.session_tokens)
            active.pop(token_digest(identity.token), None)
            account.session_tokens = active
        self.session.commit()
