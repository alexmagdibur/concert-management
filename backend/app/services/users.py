from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.entities import Account, AuditEvent, Concert, Employee
from app.repositories.account import AccountRepository
from app.repositories.concert import ConcertRepository
from app.schemas.access import AccountBlock, AccountCreate, AccountRoles, AccountShow
from app.schemas.catalog import Page
from app.schemas.concert import ConcertResponse


class UserService:
    def __init__(self, session: Session):
        self.session = session
        self.accounts = AccountRepository(session)
        self.concerts = ConcertRepository(session)

    @contextmanager
    def _write(self, actor: int | None):
        try:
            self.concerts.lock_schedule()
            if actor is not None:
                author = self.accounts.get(actor)
                if (
                    author is None
                    or not author.active
                    or not self.accounts.employee_active(author)
                    or "ADMIN" not in self.accounts.roles(actor)
                ):
                    raise HTTPException(403, "ADMIN role required")
            yield
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise HTTPException(409, "Login or account already exists") from exc
            raise
        except Exception:
            self.session.rollback()
            raise

    def _show(self, account: Account, employee: Employee, *, roles=None) -> AccountShow:
        return AccountShow(
            id=account.id,
            employee_id=employee.id,
            login=account.login,
            active=account.active and employee.active,
            full_name=employee.full_name,
            position=employee.position,
            email=employee.email,
            phone=employee.phone,
            version=employee.version,
            roles=self.accounts.roles(account.id) if roles is None else roles,
        )

    def _audit(self, actor, entity, identity, action, after, *, before=None, reason=None):
        self.session.add(
            AuditEvent(
                occurred_at=datetime.now(UTC),
                actor_id=actor,
                object_type=entity,
                object_id=identity,
                action=action,
                before_data=before,
                after_data=after,
                reason=reason,
            )
        )

    @staticmethod
    def _employee_data(employee: Employee):
        return {
            key: getattr(employee, key)
            for key in ("id", "full_name", "position", "email", "phone", "active", "version")
        }

    def list(self, limit: int, offset: int) -> Page[AccountShow]:
        query = select(Account, Employee).join(Employee, Account.employee_id == Employee.id)
        rows = self.session.execute(query.order_by(Account.id).limit(limit).offset(offset))
        return Page[AccountShow](
            items=[self._show(account, employee) for account, employee in rows],
            total=self.session.scalar(select(func.count()).select_from(Account)),
            limit=limit,
            offset=offset,
        )

    def create(self, data: AccountCreate, actor: int | None) -> AccountShow:
        encoded = hash_password(data.password.get_secret_value())
        with self._write(actor):
            if actor is None and (data.roles != ["ADMIN"] or self.accounts.has_admin()):
                raise HTTPException(
                    409, "Bootstrap requires a database without an active administrator"
                )
            now = datetime.now(UTC)
            employee = Employee(
                **data.model_dump(include={"full_name", "position", "phone", "email"}),
                active=True,
                version=1,
                created_at=now,
                updated_at=now,
            )
            self.session.add(employee)
            self.session.flush()
            account = Account(
                employee_id=employee.id, login=data.login, password_hash=encoded, active=True
            )
            self.session.add(account)
            self.session.flush()
            self.accounts.assign(account.id, data.roles)
            self.session.flush()
            result = self._show(account, employee)
            author = actor if actor is not None else account.id
            reason = "Initial administrator bootstrap" if actor is None else None
            self._audit(
                author,
                "employee",
                employee.id,
                "CREATE",
                self._employee_data(employee),
                reason=reason,
            )
            self._audit(
                author,
                "account",
                account.id,
                "CREATE",
                result.model_dump(mode="json"),
                reason=reason,
            )
            return result

    def _locked(self, identity: int, version: int):
        account = self.accounts.get(identity, lock=True)
        if account is None:
            raise HTTPException(404, "Account not found")
        employee = self.session.scalar(
            select(Employee)
            .where(Employee.id == account.employee_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if employee.version != version:
            raise HTTPException(409, "Version conflict; reload the account")
        if not (account.active and employee.active):
            raise HTTPException(409, "Account is blocked")
        return account, employee

    def _protect_last_admin(self, account: Account, roles: list[str]):
        if "ADMIN" in roles and not self.accounts.has_admin(excluding=account.id):
            raise HTTPException(409, "Cannot remove access from the last active administrator")

    def _transfer(self, employee: Employee, data: AccountBlock, actor: int):
        concerts = self.session.scalars(
            select(Concert)
            .where(
                Concert.responsible_id == employee.id,
                Concert.status.in_(("NEGOTIATING", "CONFIRMED")),
            )
            .order_by(Concert.id)
            .with_for_update()
        ).all()
        if not concerts and data.replacement_employee_id is None:
            return
        replacement = data.replacement_employee_id
        if (
            replacement is None
            or replacement == employee.id
            or not self.concerts.responsible_is_manager(replacement)
        ):
            raise HTTPException(409, "Unfinished concerts require another active manager")
        for concert in concerts:
            before = ConcertResponse.model_validate(concert).model_dump(mode="json")
            concert.responsible_id = replacement
            concert.version += 1
            concert.updated_at = datetime.now(UTC)
            self._audit(
                actor,
                "concert",
                concert.id,
                "REASSIGN",
                ConcertResponse.model_validate(concert).model_dump(mode="json"),
                before=before,
                reason=data.reason,
            )

    def block(self, identity: int, data: AccountBlock, actor: int) -> AccountShow:
        with self._write(actor):
            account, employee = self._locked(identity, data.version)
            before = self._show(account, employee)
            before_employee = self._employee_data(employee)
            self._protect_last_admin(account, before.roles)
            self._transfer(employee, data, actor)
            account.active = employee.active = False
            account.session_tokens = {}
            employee.version += 1
            employee.updated_at = datetime.now(UTC)
            result = self._show(account, employee, roles=before.roles)
            self._audit(
                actor,
                "employee",
                employee.id,
                "BLOCK",
                self._employee_data(employee),
                before=before_employee,
                reason=data.reason,
            )
            self._audit(
                actor,
                "account",
                identity,
                "BLOCK",
                result.model_dump(mode="json"),
                before=before.model_dump(mode="json"),
                reason=data.reason,
            )
            return result

    def set_roles(self, identity: int, data: AccountRoles, actor: int) -> AccountShow:
        with self._write(actor):
            account, employee = self._locked(identity, data.version)
            before = self._show(account, employee)
            if "ADMIN" not in data.roles:
                self._protect_last_admin(account, before.roles)
            if "MANAGER" in before.roles and "MANAGER" not in data.roles:
                self._transfer(employee, data, actor)
            self.accounts.assign(identity, data.roles)
            employee.version += 1
            employee.updated_at = datetime.now(UTC)
            self.session.flush()
            result = self._show(account, employee)
            self._audit(
                actor,
                "account",
                identity,
                "SET_ROLES",
                result.model_dump(mode="json"),
                before=before.model_dump(mode="json"),
                reason=data.reason,
            )
            return result
