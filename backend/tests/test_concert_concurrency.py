"""Independent PostgreSQL sessions, forced to wait together on the schedule lock."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from queue import Queue
from time import monotonic, sleep

import pytest
from concert_support import STAMP, add_contract, payload
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent, Concert, Contract
from app.repositories.concert import CONCERT_SCHEDULE_LOCK
from app.schemas.concert import ConcertCreate, ConcertTransition, ConcertUpdate
from app.schemas.contract import ContractActivate, ContractCreate
from app.services.concert import ConcertError, ConcertService
from app.services.contract import ContractError, ContractService


def compete(engine, data, jobs):
    pids = Queue()

    def worker(job):
        with Session(engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '15s'"))
            session.execute(text("SET LOCAL statement_timeout = '20s'"))
            pids.put(session.scalar(text("SELECT pg_backend_pid()")))
            try:
                result = job(ConcertService(session), data["MANAGER"]["account"])
                return 200, result
            except (ConcertError, ContractError) as exc:
                return exc.status, exc.detail

    with ThreadPoolExecutor(max_workers=2) as pool:
        blocker = engine.connect()
        try:
            blocker.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": CONCERT_SCHEDULE_LOCK}
            )
            futures = [pool.submit(worker, job) for job in jobs]
            first, second = pids.get(timeout=10), pids.get(timeout=10)
            assert first != second  # truly separate database connections
            deadline = monotonic() + 10
            while True:
                with engine.connect() as monitor:
                    waiting = monitor.scalar(
                        text("""SELECT count(*) FROM pg_locks
                        WHERE locktype='advisory' AND NOT granted AND pid IN (:first, :second)"""),
                        {"first": first, "second": second},
                    )
                if waiting == 2:
                    break
                assert monotonic() < deadline, (
                    "Both requests must actually wait on the schedule lock"
                )
                sleep(0.01)
        finally:
            blocker.rollback()
            blocker.close()
        return [future.result(timeout=20) for future in futures]


@pytest.mark.parametrize(
    "mode", ["two_confirmations", "same_concert", "two_reschedules", "confirm_vs_reschedule"]
)
def test_competing_writes_preserve_schedule_and_versions(race, mode):
    engine, data = race
    actor = data["MANAGER"]["account"]
    with Session(engine) as session:
        service = ConcertService(session)
        first = service.create(ConcertCreate(**payload(data)), actor)
        second = None
        if mode != "same_concert":
            shift = (
                0 if mode == "two_confirmations" else (10 if mode == "confirm_vs_reschedule" else 2)
            )
            second = service.create(ConcertCreate(**payload(data, shift=shift)), actor)
        for row in [first, second]:
            if row is not None:
                add_contract(session, row.id, data)
        session.commit()
        if mode in {"two_reschedules", "confirm_vs_reschedule"}:
            first = service.transition(first.id, ConcertTransition(version=1), actor, "CONFIRMED")
        if mode == "two_reschedules":
            second = service.transition(second.id, ConcertTransition(version=1), actor, "CONFIRMED")
    target = STAMP + timedelta(days=10)
    edit = {"starts_at": target, "ends_at": target + timedelta(hours=2)}
    if mode in {"two_confirmations", "same_concert"}:
        other_id = first.id if second is None else second.id
        jobs = [
            lambda svc, author: svc.transition(
                first.id, ConcertTransition(version=1), author, "CONFIRMED"
            ),
            lambda svc, author: svc.transition(
                other_id, ConcertTransition(version=1), author, "CONFIRMED"
            ),
        ]
    elif mode == "two_reschedules":
        jobs = [
            lambda svc, author: svc.update(first.id, ConcertUpdate(version=2, **edit), author),
            lambda svc, author: svc.update(second.id, ConcertUpdate(version=2, **edit), author),
        ]
    else:
        jobs = [
            lambda svc, author: svc.update(first.id, ConcertUpdate(version=2, **edit), author),
            lambda svc, author: svc.transition(
                second.id, ConcertTransition(version=1), author, "CONFIRMED"
            ),
        ]
    results = compete(engine, data, jobs)
    assert sorted(code for code, _ in results) == [200, 409]
    with Session(engine) as session:
        assert (
            session.scalar(
                text("""SELECT count(*) FROM concert a JOIN concert b ON a.id<b.id
            WHERE a.status='CONFIRMED' AND b.status='CONFIRMED'
            AND a.starts_at<b.ends_at AND b.starts_at<a.ends_at""")
            )
            == 0
        )
        rows = session.scalars(select(Concert).order_by(Concert.id)).all()
        if mode == "same_concert":
            assert len(rows) == 1 and rows[0].version == 2
        elif mode == "two_confirmations":
            assert sorted(row.version for row in rows) == [1, 2]
        elif mode == "two_reschedules":
            assert sorted(row.version for row in rows) == [2, 3]
        baseline = (
            1
            if mode == "same_concert"
            else (4 if mode == "two_reschedules" else (3 if mode == "confirm_vs_reschedule" else 2))
        )
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == baseline + 1


def test_concurrent_main_contract_activation(race):
    engine, data = race
    actor = data["MANAGER"]["account"]
    with Session(engine) as session:
        concert = ConcertService(session).create(ConcertCreate(**payload(data)), actor)
        contracts = ContractService(session)
        drafts = [
            contracts.create(
                ContractCreate(
                    number=f"MAIN-{i}",
                    signed_on=STAMP.date(),
                    concert_id=concert.id,
                    counterparty_id=data["party1"],
                    kind="MAIN_SHOW",
                    subject="Performance",
                    amount="123.45",
                    direction="IN",
                ),
                actor,
            )
            for i in range(2)
        ]

    def activation(identity):
        def run(service, actor_id):
            return ContractService(service.session).activate(
                identity, ContractActivate(version=1), actor_id
            )

        return run

    results = compete(engine, data, [activation(draft.id) for draft in drafts])
    assert sorted(code for code, _ in results) == [200, 409]
    with Session(engine) as session:
        rows = session.scalars(select(Contract)).all()
        assert sorted((row.status, row.version) for row in rows) == [("ACTIVE", 2), ("DRAFT", 1)]
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.object_type == "contract", AuditEvent.action == "ACTIVATE")
            )
            == 1
        )
        confirmed = ConcertService(session).transition(
            concert.id, ConcertTransition(version=1), actor, "CONFIRMED"
        )
        assert confirmed.status == "CONFIRMED"
