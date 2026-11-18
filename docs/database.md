# PostgreSQL schema

Source: NIRS section 1.10, pages 43-51, figure 14a-14d. Extracted reference images are in physical-model/.

Exactly 12 domain/access/history tables: employee, account, role, account_role, venue, counterparty, concert, engagement, contract, finance_category, finance_entry, audit_event. Alembic additionally owns its technical alembic_version table.

All identifiers/FKs and version are bigint. Money is numeric(14,2), Python Decimal. All timestamp fields use time zone; signed_on and occurred_on are date. JSON snapshots are jsonb. Domain field nullability follows NIRS. Eight mutable domain tables include created_at, updated_at and version.

Migration 3f52e6da10ac adds the technical account.session_tokens JSONB field with an empty object as its default. The field stores session digests and expiration times. See [access API](access-api.md).

Foreign keys use ON DELETE RESTRICT throughout, including original finance entries. No cascade deletion. account_role has a composite primary key.

Unique constraints: account.employee_id, account.login, role.code, engagement.contract_id, finance_category.code, finance_entry.request_key, contract(counterparty_id, number, signed_on). NULL request keys may repeat. The agreed machine code ACTIVE represents an effective contract; a partial unique index on contract.concert_id applies to kind MAIN_SHOW and status ACTIVE.

CHECK constraints: ADMIN/MANAGER roles; ends_at > starts_at; nonnegative budget; positive contract/engagement/entry amounts; MAIN_SHOW/SERVICE contract kind; IN/OUT directions; DRAFT/POSTED/VOID finance statuses; POSTED requires request_key; VOID requires a nonblank reason. Status sets for other objects and counterparty kinds are not invented: NIRS does not specify their machine codes in section 1.10.

Indexes follow page 47: concert(status, starts_at), venue(city), contract(concert_id, status), engagement(concert_id), finance_entry(concert_id, occurred_on), finance_entry(contract_id, occurred_on), finance_entry(original_id), audit_event(object_type, object_id, occurred_at).

Cross-row rules explicitly assigned to transactional services by NIRS remain for the service implementation: confirmation prerequisites, schedule overlap, organizer agreement, engagement/contract alignment, entry/contract alignment, refund direction and cumulative limits. POSTED edit protection, optimistic concurrency and atomic audit writes also require application services. No cross-row CHECK or fake service behavior is introduced by this schema task.

## Docker

Set POSTGRES_PASSWORD and matching DATABASE_URL in the private root .env (see .env.example). Then:

```powershell
docker compose up -d --wait
cd backend
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m alembic check
```

Compose uses PostgreSQL 18, a named persistent postgres_data volume mounted at /var/lib/postgresql, and loopback host port 5433 by default. Do not remove the volume to restart the service.

## Tests

```powershell
# Set TEST_DATABASE_URL privately to a PostgreSQL database permitting CREATE SCHEMA.
cd backend
.venv/Scripts/python -m pytest -p no:cacheprovider
.venv/Scripts/python -m ruff check --no-cache .
```

Database tests run migrations in a uniquely named temporary schema, repeat upgrade head, insert real fixtures, test rejected writes/deletions and Decimal round trips, and drop only their temporary schema. Without TEST_DATABASE_URL they are explicitly skipped.

## Verification environment

Docker is unavailable on the current host. Migrations were applied to a separate local PostgreSQL 18 cluster in ignored .local-postgres/, listening only on 127.0.0.1:55432. It uses trust authentication for local verification only and is not a production deployment. The private .env points to that database. Existing PostgreSQL services/databases were not changed.
