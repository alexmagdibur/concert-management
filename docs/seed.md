# Test-data seed (PostgreSQL only)

Run manually from backend: `python -m app.seed --confirm-test-data`. The command is never imported by application startup, migrations or Docker Compose. It never uses DATABASE_URL: SEED_DATABASE_URL is mandatory. APP_ENV defaults to production; SEED_ENABLED defaults to false.

## Setup in PowerShell

Use an empty, separate database such as concert_crm_seed. Create it with your PostgreSQL tools and apply the existing migrations to that database first. No new tables or migrations are needed for seed data.

```powershell
cd D:\coding\concert-management\backend
$env:APP_ENV = "development"
$env:SEED_ENABLED = "true"
$env:SEED_DATABASE_URL = "postgresql+psycopg://concert_crm@127.0.0.1:55432/concert_crm_seed"
# Point migrations explicitly at the SAME dedicated database:
$env:DATABASE_URL = $env:SEED_DATABASE_URL
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.seed --confirm-test-data
# Safe repeat:
.\.venv\Scripts\python.exe -m app.seed --confirm-test-data
```

The URL above is for this project's local verification cluster. For Docker, start PostgreSQL using compose.yaml and configure the actual role/password/port privately; never commit credentials. Name alone cannot prove a database is non-production: use a dedicated non-production database and role. Never enable the flags on production.

## Safety and repeatability

All data writes share one transaction. An advisory lock serializes seed invocations, table locks prevent concurrent writes during inspection. Seed uses stable negative IDs in separate ranges and fixed login/category/request keys. It does not alter sequences, delete rows, overwrite financial records, reset passwords or swallow failed inserts. On unexpected existing data or modified seed rows, it fails and rolls back. Use a fresh separate database rather than deleting existing financial data. Repeat on unchanged seed data preserves all values, including password hashes and timestamps.

There are two active test accounts (seed_v1_manager, seed_v1_admin), each with only its own role. Password hashes use salted scrypt with independently generated random passwords that are immediately discarded. There is no shared/default password, and seed does not provide login credentials. Authentication/password setup remains a separate feature.

## Dataset

2 employees, 2 accounts, 2 roles, 2 account_role links, 3 venues, 3 counterparties, 4 concerts, 4 contracts, 1 engagement, 2 categories, 4 finance entries, 4 audit events.

Concert machine codes for the seed correspond to NIRS UC04: NEGOTIATING (on approval), CONFIRMED, COMPLETED, CANCELLED. Engagement COMPLETED means work performed (UC05). Contract ACTIVE is the previously agreed effective-state code. These seed values do not introduce new schema constraints.

Confirmed/completed shows have venues, responsible manager and matching main contracts. Cancellation has a reason and keeps its contract. The service engagement has matching concert, contractor and amount. A completed show uses the NIRS control example: fee 150000.00, expense 40000.00, fee refund 50000.00. The refund retains the original concert/contract/category and reverses direction. Net result is 60000.00; net contract payment is 100000.00. A separate VOID error has a reason and is excluded from totals. Seed audit records describe explicit sample creation, not fabricated user activity.

## Tests and persistence

```powershell
$env:TEST_DATABASE_URL = $env:SEED_DATABASE_URL
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check --no-cache .
```

Integration tests run in disposable PostgreSQL schemas using Alembic, never SQLite. They cover guards, exact repeatability, real business joins, rollback, every table PK, every FK, existing UNIQUE/CHECK tests and restricted deletion. No TEST_DATABASE_URL means PostgreSQL tests are explicitly skipped.

For persistence verification on this host, the project-local PostgreSQL 18 cluster was restarted with pg_ctl; direct read-only counts were then checked before any repeated seed. All counts matched. Docker is unavailable on this host, so a Docker restart was not tested. With Docker use `docker compose restart postgres` and recheck counts without removing the named volume.
