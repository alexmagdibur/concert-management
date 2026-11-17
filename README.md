# Concert CRM

Backend scaffold for one musical artist. Requirements: the NIRS PDF in the repository root, sections 1.6 and 1.10; development rules: AGENTS.md. The 12-table physical database model is implemented. See [database documentation](docs/database.md) for constraints, Docker setup and PostgreSQL tests.

## Run (PowerShell, repository root)

```powershell
py -3.14 -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
Copy-Item .env.example .env
cd backend
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Configure APP_NAME and DATABASE_URL in the root .env. The example has no credentials; provide local PostgreSQL credentials privately. .env is ignored by Git.

GET http://127.0.0.1:8000/health returns HTTP 200 and `{"status":"ok"}`. This is an application liveness check, not a database readiness check. Swagger: http://127.0.0.1:8000/docs.

## Checks (from backend)

```powershell
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m alembic heads
```

## Database and layout

SQLAlchemy 2 uses PostgreSQL through psycopg. Provision PostgreSQL separately. get_session closes sessions; services will own transactions for related changes. No create_all is used. Alembic uses Base metadata. Apply the initial schema with `alembic upgrade head`. Future model changes require reviewed migrations.

Backend packages: core, models, schemas, repositories, services, routers. Frontend contains only pages, components, api, hooks and public directories. React and design are not implemented.
