from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.entities import Account, AccountRole, Employee, Role


class AccountRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, identity: int, *, lock: bool = False) -> Account | None:
        stmt = select(Account).where(Account.id == identity)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(stmt)

    def by_login(self, login: str) -> Account | None:
        return self.session.scalar(select(Account).where(Account.login == login))

    def employee(self, account: Account) -> Employee | None:
        return self.session.get(Employee, account.employee_id)

    def employee_active(self, account: Account) -> bool:
        return bool(
            self.session.scalar(select(Employee.active).where(Employee.id == account.employee_id))
        )

    def roles(self, account_id: int) -> list[str]:
        return list(
            self.session.scalars(
                select(Role.code)
                .join(AccountRole)
                .where(AccountRole.account_id == account_id)
                .order_by(Role.code)
            )
        )

    def assign(self, account_id: int, codes: list[str]) -> None:
        self.session.execute(delete(AccountRole).where(AccountRole.account_id == account_id))
        self.session.execute(
            insert(Role)
            .values([{"code": code, "name": code} for code in sorted(codes)])
            .on_conflict_do_nothing(index_elements=[Role.code])
        )
        roles = self.session.scalars(select(Role.id).where(Role.code.in_(codes)))
        self.session.add_all(
            AccountRole(account_id=account_id, role_id=identity) for identity in roles
        )

    def has_admin(self, *, excluding: int | None = None) -> bool:
        stmt = (
            select(Account.id)
            .join(Employee, Employee.id == Account.employee_id)
            .join(AccountRole)
            .join(Role)
            .where(Role.code == "ADMIN", Account.active.is_(True), Employee.active.is_(True))
        )
        if excluding is not None:
            stmt = stmt.where(Account.id != excluding)
        return self.session.scalar(stmt.limit(1)) is not None
