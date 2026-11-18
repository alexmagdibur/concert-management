"""Physical model from NIRS section 1.10 and figure 14 (pages 43-51)."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class Employee(Base):
    __tablename__ = "employee"
    id = Column(BigInteger, primary_key=True)
    full_name = Column(String(150), nullable=False)
    position = Column(String(80), nullable=False)
    phone = Column(String(32), nullable=True)
    email = Column(String(254), nullable=True)
    active = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(BigInteger, nullable=False)
    __table_args__ = ()


class Account(Base):
    __tablename__ = "account"
    id = Column(BigInteger, primary_key=True)
    employee_id = Column(
        BigInteger, ForeignKey("employee.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    login = Column(String(80), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False)
    session_tokens = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    __table_args__ = ()


class Role(Base):
    __tablename__ = "role"
    id = Column(BigInteger, primary_key=True)
    code = Column(String(20), nullable=False, unique=True)
    name = Column(String(80), nullable=False)
    __table_args__ = (CheckConstraint("code IN ('ADMIN', 'MANAGER')", name="ck_role_1"),)


class Venue(Base):
    __tablename__ = "venue"
    id = Column(BigInteger, primary_key=True)
    name = Column(String(200), nullable=False)
    city = Column(String(100), nullable=False)
    address = Column(String(300), nullable=False)
    capacity = Column(Integer, nullable=True)
    archived = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(BigInteger, nullable=False)
    __table_args__ = ()


class Counterparty(Base):
    __tablename__ = "counterparty"
    id = Column(BigInteger, primary_key=True)
    name = Column(String(200), nullable=False)
    kind = Column(String(20), nullable=False)
    phone = Column(String(32), nullable=True)
    email = Column(String(254), nullable=True)
    details = Column(Text, nullable=True)
    archived = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(BigInteger, nullable=False)
    __table_args__ = ()


class Concert(Base):
    __tablename__ = "concert"
    id = Column(BigInteger, primary_key=True)
    name = Column(String(200), nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    venue_id = Column(BigInteger, ForeignKey("venue.id", ondelete="RESTRICT"), nullable=True)
    proposed_organizer_id = Column(
        BigInteger, ForeignKey("counterparty.id", ondelete="RESTRICT"), nullable=True
    )
    responsible_id = Column(
        BigInteger, ForeignKey("employee.id", ondelete="RESTRICT"), nullable=False
    )
    expense_budget = Column(Numeric(14, 2), nullable=False)
    status = Column(String(20), nullable=False)
    cancel_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_concert_1"),
        CheckConstraint("expense_budget >= 0", name="ck_concert_2"),
    )


class Contract(Base):
    __tablename__ = "contract"
    id = Column(BigInteger, primary_key=True)
    number = Column(String(80), nullable=False)
    signed_on = Column(Date, nullable=False)
    concert_id = Column(BigInteger, ForeignKey("concert.id", ondelete="RESTRICT"), nullable=False)
    counterparty_id = Column(
        BigInteger, ForeignKey("counterparty.id", ondelete="RESTRICT"), nullable=False
    )
    kind = Column(String(20), nullable=False)
    subject = Column(Text, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    direction = Column(String(3), nullable=False)
    status = Column(String(20), nullable=False)
    close_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_contract_1"),
        CheckConstraint("kind IN ('MAIN_SHOW', 'SERVICE')", name="ck_contract_2"),
        CheckConstraint("direction IN ('IN', 'OUT')", name="ck_contract_3"),
        UniqueConstraint("counterparty_id", "number", "signed_on", name="uq_contract_identity"),
    )


class Engagement(Base):
    __tablename__ = "engagement"
    id = Column(BigInteger, primary_key=True)
    concert_id = Column(BigInteger, ForeignKey("concert.id", ondelete="RESTRICT"), nullable=False)
    counterparty_id = Column(
        BigInteger, ForeignKey("counterparty.id", ondelete="RESTRICT"), nullable=False
    )
    description = Column(Text, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)
    agreed_amount = Column(Numeric(14, 2), nullable=False)
    contract_id = Column(
        BigInteger, ForeignKey("contract.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    status = Column(String(20), nullable=False)
    cancel_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(BigInteger, nullable=False)
    __table_args__ = (CheckConstraint("agreed_amount > 0", name="ck_engagement_1"),)


class FinanceCategory(Base):
    __tablename__ = "finance_category"
    id = Column(BigInteger, primary_key=True)
    code = Column(String(40), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    normal_direction = Column(String(3), nullable=False)
    archived = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint("normal_direction IN ('IN', 'OUT')", name="ck_finance_category_1"),
    )


class FinanceEntry(Base):
    __tablename__ = "finance_entry"
    id = Column(BigInteger, primary_key=True)
    concert_id = Column(BigInteger, ForeignKey("concert.id", ondelete="RESTRICT"), nullable=False)
    contract_id = Column(BigInteger, ForeignKey("contract.id", ondelete="RESTRICT"), nullable=True)
    category_id = Column(
        BigInteger, ForeignKey("finance_category.id", ondelete="RESTRICT"), nullable=False
    )
    occurred_on = Column(Date, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    direction = Column(String(3), nullable=False)
    basis = Column(Text, nullable=False)
    original_id = Column(
        BigInteger, ForeignKey("finance_entry.id", ondelete="RESTRICT"), nullable=True
    )
    status = Column(String(10), nullable=False)
    void_reason = Column(Text, nullable=True)
    created_by = Column(BigInteger, ForeignKey("account.id", ondelete="RESTRICT"), nullable=False)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    request_key = Column(String(80), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_finance_entry_1"),
        CheckConstraint("direction IN ('IN', 'OUT')", name="ck_finance_entry_2"),
        CheckConstraint("status IN ('DRAFT', 'POSTED', 'VOID')", name="ck_finance_entry_3"),
        CheckConstraint("status <> 'POSTED' OR request_key IS NOT NULL", name="ck_finance_entry_4"),
        CheckConstraint(
            "status <> 'VOID' OR (void_reason IS NOT NULL AND length(trim(void_reason)) > 0)",
            name="ck_finance_entry_5",
        ),
    )


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id = Column(BigInteger, primary_key=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    actor_id = Column(BigInteger, ForeignKey("account.id", ondelete="RESTRICT"), nullable=False)
    object_type = Column(String(40), nullable=False)
    object_id = Column(BigInteger, nullable=False)
    action = Column(String(40), nullable=False)
    before_data = Column(JSONB, nullable=True)
    after_data = Column(JSONB, nullable=True)
    reason = Column(Text, nullable=True)
    __table_args__ = ()


class AccountRole(Base):
    __tablename__ = "account_role"
    account_id = Column(BigInteger, ForeignKey("account.id", ondelete="RESTRICT"), primary_key=True)
    role_id = Column(BigInteger, ForeignKey("role.id", ondelete="RESTRICT"), primary_key=True)


Index(
    "ix_concert_status_starts_at",
    Base.metadata.tables["concert"].c.status,
    Base.metadata.tables["concert"].c.starts_at,
)
Index("ix_venue_city", Base.metadata.tables["venue"].c.city)
Index(
    "ix_contract_concert_id_status",
    Base.metadata.tables["contract"].c.concert_id,
    Base.metadata.tables["contract"].c.status,
)
Index("ix_engagement_concert_id", Base.metadata.tables["engagement"].c.concert_id)
Index(
    "ix_finance_entry_concert_id_occurred_on",
    Base.metadata.tables["finance_entry"].c.concert_id,
    Base.metadata.tables["finance_entry"].c.occurred_on,
)
Index(
    "ix_finance_entry_contract_id_occurred_on",
    Base.metadata.tables["finance_entry"].c.contract_id,
    Base.metadata.tables["finance_entry"].c.occurred_on,
)
Index("ix_finance_entry_original_id", Base.metadata.tables["finance_entry"].c.original_id)
Index(
    "ix_audit_event_object_type_object_id_occurred_at",
    Base.metadata.tables["audit_event"].c.object_type,
    Base.metadata.tables["audit_event"].c.object_id,
    Base.metadata.tables["audit_event"].c.occurred_at,
)

# ACTIVE is the agreed machine code for an effective contract.
Index(
    "uq_contract_active_main",
    Contract.concert_id,
    unique=True,
    postgresql_where=text("kind = 'MAIN_SHOW' AND status = 'ACTIVE'"),
)
