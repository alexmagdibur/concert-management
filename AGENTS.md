
# Concert CRM — development rules

## Project
Concert Management CRM for a single musical artist.

The primary source of requirements is the NIRS document in docs/.
Follow its database model, business rules, FR010–FR120 and UC01–UC11.

## Stack
- Python / FastAPI
- PostgreSQL
- SQLAlchemy 2
- Alembic
- Pydantic
- React / TypeScript / Vite
- Tailwind CSS / shadcn-ui
- Docker Compose
- Pytest

## Architecture
- Modular monolith
- Backend: routers, services, repositories, schemas, models
- Frontend: pages, components, api, hooks
- Database schema managed only with Alembic

## Strict rules
1. PostgreSQL is the source of truth.
2. Do not use mock data in production functionality.
3. Use Decimal and NUMERIC(14,2) for monetary values.
4. Do not physically delete referenced financial records.
5. Enforce business rules on the backend.
6. Use transactions for related database changes.
7. Preserve the 12-table database model from NIRS.
8. Do not implement ticket sales or payments.
9. Do not modify unrelated modules.
10. Do not replace failed operations with fake success responses.
11. Do not silently change requirements.
12. Never commit passwords, credentials or .env files.

## Workflow for every task
1. Inspect the existing project.
2. Read the relevant NIRS requirements.
3. Implement only the requested scope.
4. Add or update tests.
5. Run the relevant tests and linters.
6. Fix errors.
7. Summarize changed files, test results and remaining limitations.
8. Do not claim a test passed unless it actually ran.

If blocked by a missing requirement or unavailable tool,
explain the blocker instead of inventing behavior.
