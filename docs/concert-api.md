# Concert API: FR040, FR050, UC04

The module uses the existing concert, contract, employee/account/role, venue, counterparty and audit_event tables. Access uses the PostgreSQL-backed MANAGER session dependency. Use the [contract API](contract-api.md) to create and activate the main contract before confirming a concert.

## Routes

| Method | Route | Result |
| --- | --- | --- |
| POST | /concert | Create in NEGOTIATING (201) |
| GET | /concert | Paginated/filterable list (200) |
| GET | /concert/{id} | Card (200) |
| PATCH | /concert/{id} | Versioned partial update (200) |
| POST | /concert/{id}/confirm | Confirm (200) |
| POST | /concert/{id}/complete | Mark performed (200) |
| POST | /concert/{id}/cancel | Cancel with reason (200) |

There is no DELETE route, and state cannot be changed through POST/PATCH data fields.

## Data

Create requires name (1-200 characters), timezone-aware starts_at and ends_at (end strictly after start), responsible_id, and expense_budget (Decimal, nonnegative NUMERIC(14,2), at most 999999999999.99). venue_id and proposed_organizer_id may be null while negotiating. Negative IDs from the seed are supported.

```json
{
  "name": "Concert",
  "starts_at": "2027-03-01T18:00:00+03:00",
  "ends_at": "2027-03-01T20:00:00+03:00",
  "venue_id": null,
  "proposed_organizer_id": null,
  "responsible_id": 1,
  "expense_budget": "100000.00"
}
```

PATCH requires the current integer version and at least one changed field. Supported fields are name, starts_at, ends_at, venue_id, proposed_organizer_id, responsible_id and expense_budget. Only venue/organizer may be cleared with null. Partial time changes are checked against the merged interval, not just the supplied field.

```json
{"version":1,"name":"Corrected name","venue_id":2}
```

Confirmation and completion bodies: `{"version":2}`. Cancellation: `{"version":2,"reason":"Organizer cancellation"}`. Whitespace-only reasons are rejected. Responses use explicit Pydantic DTOs with UTC dates, Decimal budget, status, cancel_reason and version; no unfiltered ORM serialization.

## Lifecycle

Existing machine codes are retained:

| Source | Action | Destination |
| --- | --- | --- |
| NEGOTIATING (on approval) | confirm | CONFIRMED |
| NEGOTIATING | cancel | CANCELLED |
| CONFIRMED | complete | COMPLETED |
| CONFIRMED | cancel | CANCELLED |

Other/repeated state transitions are rejected (409). Completion is allowed only after ends_at, implementing UC04's action after performance. Cancellation never changes/deletes contracts or financial entries and does not imply a refund or release of contractual obligations.

New assignments require existing non-archived venue/organizer and an active employee with an active MANAGER account. Archived historical references remain readable and are not removed by unrelated edits. Confirmation requires an existing venue, active responsible manager and exactly one real ACTIVE MAIN_SHOW contract for this concert, matching the non-null organizer and IN direction. Missing/draft/closed/service-only/other-concert contracts cannot satisfy confirmation. No contract is invented, auto-created or automatically activated.

Confirmed edits repeat all confirmation checks, including organizer agreement and schedule. Confirmed intervals are half-open [starts_at, ends_at): touching endpoints are allowed; every actual intersection is rejected, regardless of venue or city. Negotiating/cancelled/completed rows do not participate in the confirmed schedule check.

## Corrections after completion/cancellation

As explicitly requested, COMPLETED and CANCELLED cards may be corrected using the same versioned PATCH and atomic UPDATE audit. Such corrections never change status, reset the cancellation reason or modify contracts/payments. A performed concert retains a venue/organizer and cannot be moved to the future. Changing an organizer in any state must remain consistent with an existing ACTIVE MAIN_SHOW contract. Closed historical contracts do not need to be reactivated for ordinary performed-card corrections.

## Search

GET /concert accepts starts_from (inclusive), starts_before (exclusive), city (literal case-insensitive substring), status, limit (1-100, default 20), offset (nonnegative, default 0). The period filters concert START time; both boundaries, if given, must be aware datetimes in increasing order. Period and city are combined with AND. Venue-less concerts remain in unfiltered results; city filtering requires a linked venue. Archived venues still support historical search. Order is starts_at, then id. Result: items, total, limit, offset. Unicode search uses PostgreSQL 18 built-in pg_unicode_fast collation and escaped parameterized LIKE values.

## Atomicity and concurrency

All concert mutations first acquire pg_advisory_xact_lock(810004) for the single artist, then SELECT FOR UPDATE on an existing concert, and compare expected version using a refreshed row. Confirmation/confirmed editing read actual prerequisite records under shared row locks, check the schedule and save the new version/status plus real actor audit data in one database transaction. Failure rolls everything back. The shared schedule lock also covers cancellation/completion and ordinary edits, so schedule changes cannot race confirmation. Engine isolation is explicitly READ COMMITTED so a waiter sees the winner's commit after acquiring the advisory lock.

Contract mutations use the same schedule-lock-before-row-lock protocol. Future employee mutation services must follow it when changing confirmation prerequisites. Direct SQL writers can bypass application protocols.

## Errors and tests

401/403: existing authentication/role checks. 404: concert missing. 409: stale version, invalid transition, unavailable/invalid confirmation prerequisites, overlap, archived new selection or invalid manager assignment. 422: DTO errors, missing reference, invalid merged time interval. Unexpected database errors remain real errors, never fake success responses.

Tests run against PostgreSQL with Alembic-managed disposable schemas. API tests verify lifecycle, failure atomicity, real contracts/links, partial edits, versions, precision/time validation, search, access and audit. Concurrency tests use two independent sessions blocked simultaneously on the same real PostgreSQL advisory lock; they verify two confirmations, same-concert confirmation, two reschedules and confirm-versus-reschedule. No SQLite or mock storage is used.

```powershell
cd backend
# Set TEST_DATABASE_URL privately to your PostgreSQL test database.
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q
.\.venv\Scripts\python.exe -m ruff check --no-cache .
.\.venv\Scripts\python.exe -m alembic check
```
