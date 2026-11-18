from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from auth_support import NO_SESSION, session_headers
from concert_support import STAMP, add_contract, payload
from sqlalchemy import text
from test_finance_api import operation, setup_records

from app.models.entities import Concert, FinanceEntry

PERIOD = {"date_from": "2020-01-01", "date_to": "2020-01-31", "as_of": "2020-01-31"}
TECH = {"created_at": STAMP, "updated_at": STAMP, "version": 1}


def seed_concert(session, data, name, *, day=0, status="COMPLETED", budget="100.00"):
    start = STAMP + timedelta(days=day)
    row = Concert(
        name=name,
        starts_at=start,
        ends_at=start + timedelta(hours=2),
        status=status,
        expense_budget=Decimal(budget),
        responsible_id=data["MANAGER"]["employee"],
        venue_id=data["venue1"],
        **TECH,
    )
    session.add(row)
    session.flush()
    return row.id


def seed_entry(
    session,
    data,
    concert,
    category,
    key,
    amount,
    *,
    direction="OUT",
    day=0,
    status="POSTED",
    original_id=None,
):
    row = FinanceEntry(
        concert_id=concert,
        category_id=category,
        amount=Decimal(amount),
        occurred_on=STAMP.date() + timedelta(days=day),
        request_key=key if status != "DRAFT" else None,
        direction=direction,
        status=status,
        original_id=original_id,
        basis="Report fixture",
        void_reason="Incorrect entry" if status == "VOID" else None,
        created_by=data["MANAGER"]["account"],
        posted_at=STAMP if status != "DRAFT" else None,
        **TECH,
    )
    session.add(row)
    session.flush()
    return row.id


def record(client, concert, category, key, amount, **changes):
    response = client.post(
        "/finance",
        json=operation(
            concert, category, request_key=key, amount=amount, occurred_on="2020-01-10", **changes
        ),
    )
    assert response.status_code == 201, response.text
    return response.json()


def refund(client, original, key, amount, occurred_on):
    response = client.post(
        f"/finance/{original['id']}/refund",
        json={
            "request_key": key,
            "amount": amount,
            "occurred_on": occurred_on,
            "basis": "Bank refund",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_report_control_example_and_as_of(concert_api):
    client, session, data = concert_api
    concert, categories = setup_records(client, data)
    contract = add_contract(session, concert, data)
    session.commit()
    incoming = record(
        client, concert, categories["IN"], "fee", "150000.00", contract_id=contract.id
    )
    expense = record(client, concert, categories["OUT"], "expense", "40000.00", direction="OUT")
    endpoint = f"/concert/{concert}/finance/report"
    result = client.get(endpoint, params=PERIOD)
    assert result.status_code == 200, result.text
    initial = result.json()
    assert (initial["income"], initial["expenses"], initial["net"]) == (
        "150000.00",
        "40000.00",
        "110000.00",
    )
    assert initial["contracts"][0]["net_paid"] == "150000.00"
    assert initial["contracts"][0]["unpaid"] == "350000.00"
    assert initial["actual_expenses"] == "40000.00" and initial["budget_remaining"] == "60000.25"
    fee_refund = refund(client, incoming, "fee-refund", "50000.00", "2020-01-20")
    refund(client, expense, "expense-refund", "10000.00", "2020-01-21")
    ignored = record(client, concert, categories["IN"], "error", "50000.00")
    assert (
        client.post(
            f"/finance/{ignored['id']}/void", json={"version": 1, "reason": "Error"}
        ).status_code
        == 200
    )
    draft = client.post(
        "/finance/draft", json=operation(concert, categories["OUT"], direction="OUT")
    )
    assert draft.status_code == 201
    current = client.get(endpoint, params=PERIOD | {"limit": 1, "offset": 2}).json()
    assert current["net"] == "70000.00"
    assert current["actual_expenses"] == "30000.00"
    assert current["contracts"][0]["net_paid"] == "100000.00"
    assert current["contracts"][0]["unpaid"] == "400000.00"
    assert current["operations"]["total"] == 4 and current["operations"]["items"] == [fee_refund]
    earlier = client.get(endpoint, params=PERIOD | {"as_of": "2020-01-10"}).json()
    assert earlier["net"] == "70000.00"
    assert earlier["contracts"][0]["unpaid"] == "350000.00"
    empty = client.get(endpoint, params=PERIOD | {"date_from": "2020-01-22"}).json()
    assert empty["operations"]["items"] == [] and empty["net"] == "0.00"
    assert empty["contracts"][0]["net_paid"] == "100000.00"
    inclusive = client.get(
        endpoint,
        params=PERIOD
        | {
            "date_from": "2020-01-20",
            "date_to": "2020-01-20",
        },
    ).json()
    assert inclusive["operations"]["items"] == [fee_refund]


def test_dashboard_matches_postgresql_and_concert_reports(concert_api):
    client, session, data = concert_api
    first, categories = setup_records(client, data)
    second = seed_concert(session, data, "Второй концерт", day=40)
    future_day = (datetime.now(UTC).date() - STAMP.date()).days + 30
    seed_concert(session, data, "Будущий", day=future_day, status="NEGOTIATING")
    seed_concert(session, data, "Подтверждённый", day=future_day + 1, status="CONFIRMED")
    seed_concert(session, data, "Отменённый", day=future_day + 2, status="CANCELLED")
    original = seed_entry(
        session, data, first, categories["IN"], "dashboard-in", "150000.00", direction="IN", day=9
    )
    seed_entry(session, data, first, categories["OUT"], "dashboard-out", "40000.00", day=9)
    seed_entry(
        session,
        data,
        first,
        categories["IN"],
        "dashboard-refund",
        "10000.00",
        original_id=original,
        day=10,
    )
    seed_entry(session, data, second, categories["OUT"], "dashboard-feb", "5000.01", day=40)
    seed_entry(
        session,
        data,
        second,
        categories["IN"],
        "dashboard-void",
        "500000.00",
        direction="IN",
        day=40,
        status="VOID",
    )
    seed_entry(
        session,
        data,
        second,
        categories["OUT"],
        "dashboard-draft",
        "20.00",
        day=40,
        status="DRAFT",
    )
    session.commit()
    period = {"date_from": "2020-01-10", "date_to": "2020-02-29"}
    response = client.get("/dashboard", params=period)
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["upcoming_count"] == 2
    assert summary["months"] == [
        {"month": "2020-01-01", "income": "150000.00", "expenses": "50000.00", "net": "100000.00"},
        {"month": "2020-02-01", "income": "0.00", "expenses": "5000.01", "net": "-5000.01"},
    ]
    reports = [
        client.get(
            f"/concert/{concert}/finance/report", params=period | {"as_of": period["date_to"]}
        )
        for concert in (first, second)
    ]
    assert all(report.status_code == 200 for report in reports)
    for field in ("income", "expenses", "net"):
        assert Decimal(summary[field]) == sum(Decimal(report.json()[field]) for report in reports)
    income, expenses = session.execute(
        text("""
        SELECT sum(amount) FILTER (WHERE direction = 'IN'),
               sum(amount) FILTER (WHERE direction = 'OUT')
        FROM finance_entry
        WHERE status = 'POSTED' AND occurred_on BETWEEN DATE '2020-01-10' AND DATE '2020-02-29'
    """)
    ).one()
    assert (Decimal(summary["income"]), Decimal(summary["expenses"]), Decimal(summary["net"])) == (
        income,
        expenses,
        income - expenses,
    )
    empty = client.get("/dashboard", params={"date_from": "2020-03-01", "date_to": "2020-03-31"})
    assert empty.json()["months"] == [] and empty.json()["net"] == "0.00"
    assert client.get("/dashboard", params=period | {"date_to": "2022-01-01"}).status_code == 422
    assert client.get("/dashboard", params=period, headers=NO_SESSION).status_code == 401
    assert (
        client.get(
            "/dashboard", params=period, headers=session_headers("test_ADMIN", data["password"])
        ).status_code
        == 403
    )


def test_outgoing_balance_and_overpayment(concert_api):
    client, session, data = concert_api
    concert, categories = setup_records(client, data)
    contract = add_contract(
        session, concert, data, kind="SERVICE", direction="OUT", amount=Decimal("100.00")
    )
    unpaid = add_contract(
        session,
        concert,
        data,
        number="UNPAID",
        kind="SERVICE",
        direction="OUT",
        amount=Decimal("50.00"),
    )
    session.commit()
    expense = record(
        client,
        concert,
        categories["OUT"],
        "expense",
        "150.00",
        direction="OUT",
        contract_id=contract.id,
    )
    refund(client, expense, "refund", "20.00", "2020-01-11")
    result = client.get(f"/concert/{concert}/finance/report", params=PERIOD).json()
    balances = {item["contract_id"]: item for item in result["contracts"]}
    assert balances[contract.id]["net_paid"] == "130.00"
    assert balances[contract.id]["unpaid"] == "0.00"
    assert balances[contract.id]["overpaid"] == "30.00"
    assert balances[unpaid.id]["net_paid"] == "0.00"
    assert balances[unpaid.id]["unpaid"] == "50.00"


def test_ranking_orders_ties_limits_and_cutoff(concert_api):
    client, session, data = concert_api
    _, categories = setup_records(client, data)
    for name, day, amount, direction in (
        ("tie-later", 4, "20", "IN"),
        ("tie-first", 2, "20", "IN"),
        ("tie-second", 2, "20", "IN"),
        ("loss", 3, "50", "OUT"),
        ("zero", 3, None, "IN"),
        ("small", 5, "5", "IN"),
    ):
        concert = seed_concert(session, data, name, day=day)
        if amount is not None:
            seed_entry(
                session,
                data,
                concert,
                categories[direction],
                name,
                amount,
                direction=direction,
                day=10,
            )
        seed_entry(
            session,
            data,
            concert,
            categories["IN"],
            f"{name}-void",
            "999",
            direction="IN",
            day=10,
            status="VOID",
        )
        seed_entry(
            session, data, concert, categories["IN"], f"{name}-later", "999", direction="IN", day=20
        )
    seed_concert(session, data, "future-period", day=50)
    seed_concert(session, data, "planned", status="NEGOTIATING")
    session.commit()
    response = client.get("/analytics/ranking", params=PERIOD | {"as_of": "2020-01-11"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["count"] == 6
    assert [row["name"] for row in result["best"]] == ["tie-first", "tie-second", "tie-later"]
    assert [row["name"] for row in result["worst"]] == ["loss", "zero", "small"]
    assert [Decimal(row["net"]) for row in result["worst"]] == [-50, 0, 5]
    short = client.get("/analytics/ranking", params=PERIOD | {"date_to": "2020-01-03"}).json()
    assert short["count"] == len(short["best"]) == len(short["worst"]) == 2
    empty = client.get(
        "/analytics/ranking",
        params=PERIOD
        | {
            "date_from": "2020-03-01",
            "date_to": "2020-03-02",
        },
    ).json()
    assert empty["count"] == 0 and empty["best"] == empty["worst"] == []


@pytest.mark.parametrize(
    ("n", "extra", "reason"),
    [
        (9, None, "insufficient_observations"),
        (10, "no_entries", "incomplete_history"),
        (10, "draft_expense", "incomplete_history"),
        (10, "zero_budget", "budget_required"),
        (10, None, None),
    ],
)
def test_forecast_against_independent_t_example(concert_api, n, extra, reason):
    client, session, data = concert_api
    _, categories = setup_records(client, data)
    target = seed_concert(
        session,
        data,
        "Target",
        status="NEGOTIATING",
        budget="0" if extra == "zero_budget" else "1000",
    )
    for i in range(1, n + 1):
        concert = seed_concert(session, data, f"Past {i}")
        expense = seed_entry(
            session,
            data,
            concert,
            categories["OUT"],
            f"expense-{i}",
            str(10 * i + (5 if i == 1 else 0)),
        )
        if i == 1:
            fee = seed_entry(session, data, concert, categories["IN"], "fee", "100", direction="IN")
            seed_entry(
                session,
                data,
                concert,
                categories["OUT"],
                "cost-refund",
                "5",
                direction="IN",
                original_id=expense,
            )
            seed_entry(
                session, data, concert, categories["IN"], "fee-refund", "30", original_id=fee
            )
            seed_entry(session, data, concert, categories["OUT"], "void-cost", "999", status="VOID")
            seed_entry(session, data, concert, categories["OUT"], "later-cost", "999", day=31)
    if extra in {"no_entries", "draft_expense"}:
        bad = seed_concert(session, data, "Incomplete")
        if extra == "draft_expense":
            seed_entry(session, data, bad, categories["OUT"], "posted-cost", "10")
            seed_entry(session, data, bad, categories["OUT"], "draft-cost", "10", status="DRAFT")
    seed_concert(session, data, "Zero budget", budget="0")
    seed_concert(session, data, "Cancelled", status="CANCELLED")
    session.commit()
    response = client.get(f"/concert/{target}/finance/forecast", params=PERIOD)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["n"] == n and result["reason"] == reason
    assert result["incomplete_count"] == int(extra in {"no_entries", "draft_expense"})
    if reason:
        assert result["forecast"] is None and result["message"]
        return
    estimate = result["forecast"]
    # For ratios 0.1..1.0, mean=0.55, sample variance=11/120 and t(9)=2.26215716285.
    assert Decimal(estimate["mean_ratio"]) == Decimal("0.55")
    assert float(estimate["ratio_ci_lower"]) == pytest.approx(0.33341494102783165, abs=1e-11)
    assert float(estimate["ratio_ci_upper"]) == pytest.approx(0.7665850589721684, abs=1e-11)
    assert (estimate["expected_expenses"], estimate["ci_lower"], estimate["ci_upper"]) == (
        "550.00",
        "333.41",
        "766.59",
    )
    assert estimate["interval_kind"] == "confidence_interval_for_mean"


def test_report_validation_and_access(concert_api):
    client, session, data = concert_api
    concert = seed_concert(session, data, "Completed")
    session.commit()
    paths = (
        f"/concert/{concert}/finance/report",
        "/analytics/ranking",
        f"/concert/{concert}/finance/forecast",
    )
    for path in paths:
        assert client.get(path, params=PERIOD | {"date_to": "2019-01-01"}).status_code == 422
        assert client.get(path, params=PERIOD | {"as_of": "2020-02-30"}).status_code == 422
        assert client.get(path, params=PERIOD, headers=NO_SESSION).status_code == 401
        assert (
            client.get(
                path, params=PERIOD, headers=session_headers("test_ADMIN", data["password"])
            ).status_code
            == 403
        )
    assert client.get(paths[-1], params=PERIOD).status_code == 409
    assert client.get("/concert/999999/finance/report", params=PERIOD).status_code == 404
    assert client.get("/concert/999999/finance/forecast", params=PERIOD).status_code == 404


def test_combined_search_reuses_parameterized_filters(concert_api):
    client, session, data = concert_api
    match = seed_concert(session, data, "Матч_%", day=1)
    unrelated = seed_concert(session, data, "Outside", day=40)
    kazan = client.post("/concert", json=payload(data, shift=2, venue_id=data["venue2"]))
    assert kazan.status_code == 201
    add_contract(session, match, data, number="Exact_%")
    add_contract(session, unrelated, data, number="Exact_%", counterparty_id=data["party2"])
    add_contract(session, match, data, number="Other", status="DRAFT")
    session.commit()
    found = client.get(
        "/concert",
        params={
            "starts_from": "2020-01-01T00:00:00Z",
            "starts_before": "2020-02-01T00:00:00Z",
            "city": "MOSCOW",
            "q": "МАТЧ_%",
        },
    ).json()
    assert [row["id"] for row in found["items"]] == [match]
    assert client.get("/concert", params={"q": "' OR 1=1 --"}).json()["total"] == 0
    params = {"number": "_%", "counterparty": "organizer 1"}
    found = client.get("/contract", params=params).json()
    assert [row["concert_id"] for row in found["items"]] == [match]
    assert (
        client.get("/contract", params=params | {"counterparty": "' OR 1=1 --"}).json()["total"]
        == 0
    )
