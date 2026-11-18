# Catalog REST API: FR030 / UC03

Three modules have separate schemas, repositories, services and routers. Shared code handles pagination, transactions, serialization and audit without changing the 12-table physical model. No frontend or DELETE endpoint is added.

## Routes

Replace `{catalog}` with `venue`, `counterparty` or `finance_category`:

| Method | Path | Result |
| --- | --- | --- |
| GET | /{catalog} | Paginated active records |
| GET | /{catalog}/{id} | One record, including archived records |
| POST | /{catalog} | Create (201) |
| PATCH | /{catalog}/{id} | Partial update (200) |
| POST | /{catalog}/{id}/archive | Archive (200) |

List parameters: q (literal substring, max 300), limit (1-100, default 20), offset (default 0), archived (default false; true selects only archived records). Results contain items, total, limit, offset; order is always ascending ID. Search uses parameters, escapes LIKE wildcards and uses PostgreSQL 18 built-in pg_unicode_fast collation for Unicode lowercase independent of database locale.

Search fields: venue name/city/address; counterparty name/kind/phone/email/details; finance_category code/name.

## Bodies

Venue creation: name (1-200), city (1-100), address (1-300), optional capacity (nonnegative integer).

Counterparty creation: name (1-200), kind (1-20), optional phone (up to 32), email (valid email, up to 254), details. No invented kind enum is imposed; NIRS does not define machine codes for it.

Finance category creation: code (1-40), name (1-100), normal_direction (IN or OUT).

Example venue:

```json
{"name":"Concert Hall","city":"Moscow","address":"Example street","capacity":500}
```

PATCH requires current version and at least one changed field:

```json
{"version":1,"name":"New name"}
```

Archive body:

```json
{"version":2}
```

Nullable fields can be cleared with null; required fields cannot. Unknown properties are rejected. Clients cannot set archived, timestamps or IDs. Responses are explicit Pydantic models, with UTC timestamps and version. Responses do not expose related ORM data.

## Business checks and transactions

UC03 calls for possible duplicate detection but does not specify exact identity tuples. This API uses trimmed, Unicode casefolded tuples: venue(name, city, address), counterparty(name, kind), finance_category(code). Archived entries participate in these checks. This is application duplicate detection, not additional database UNIQUE constraints. API writers take a per-catalog PostgreSQL transaction advisory lock; direct SQL writers do not follow that application policy. Existing database UNIQUE constraints remain authoritative.

Updates/archive lock the row and compare version (409 on stale writes). Every successful change increments version and sets updated_at. Directory changes and audit_event (real authenticated actor, before/after snapshots) commit atomically; failures roll back. Repeating archive with the current version is a no-op. Archived records keep their identifiers and all existing concert/contract/finance links. They are excluded from the default selection list; no restoration endpoint is introduced.

## Access

Catalog endpoints require a MANAGER session. See [access API](access-api.md) for login, CSRF and manager provisioning.

## Errors and verification

401 missing/invalid credentials or inactive account/employee; 403 missing MANAGER role; 404 missing record; 409 duplicate/version conflict; 422 request validation; 405 DELETE unsupported. Unexpected database failures propagate as failures, never fake successes.

Tests use real PostgreSQL in Alembic-managed disposable schemas. They cover session authentication, roles/blocked employees, CRUD, all three catalogs, pagination, literal/Unicode search, validation, duplicates, stale versions, audit atomicity, and archival of records referenced by real concert/contract/finance rows. No SQLite or mock storage is used.
