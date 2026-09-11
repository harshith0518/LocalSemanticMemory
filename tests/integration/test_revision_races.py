from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

from sqlalchemy import event, select, update

from jarvis.db import make_engine
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.models import ClaimRecord, Policy
from jarvis.services import Service


def test_control_commit_before_supported_write_rejects_stale_policy(
    service, normal, proposal, settings, engine
):
    attempting_lock = Barrier(2, timeout=10)
    worker_engine = make_engine(settings)

    def before_lock(connection, cursor, statement, parameters, context, many):
        if "jarvis.policies" in statement and "FOR UPDATE" in statement:
            attempting_lock.wait()

    event.listen(worker_engine, "before_cursor_execute", before_lock)
    try:
        with engine.connect() as control, ThreadPoolExecutor(max_workers=1) as pool:
            transaction = control.begin()
            control.execute(
                select(Policy).where(Policy.owner_id == normal.owner_id).with_for_update()
            )
            control.execute(
                update(Policy).where(Policy.owner_id == normal.owner_id).values(revision=1)
            )
            future = pool.submit(Service(worker_engine).commit_claim, normal, proposal)
            attempting_lock.wait()  # Worker is about to ask PG for the already-held row lock.
            transaction.commit()
            try:
                future.result(timeout=10)
                raise AssertionError("Stale write unexpectedly committed")
            except ApplicationError as error:
                assert error.code is ErrorCode.STALE_REVISION
        with engine.connect() as connection:
            assert connection.execute(select(ClaimRecord)).all() == []
    finally:
        event.remove(worker_engine, "before_cursor_execute", before_lock)
        worker_engine.dispose()


def test_supported_write_holds_guard_until_commit_before_control(
    service, normal, proposal, settings, engine
):
    writer_locked = Barrier(2, timeout=10)
    release_writer = Barrier(2, timeout=10)
    control_attempt = Barrier(2, timeout=10)
    writer_engine, control_engine = make_engine(settings), make_engine(settings)

    def after_writer_lock(connection, cursor, statement, parameters, context, many):
        if "jarvis.policies" in statement and "FOR UPDATE" in statement:
            writer_locked.wait()
            release_writer.wait()

    def before_control_lock(connection, cursor, statement, parameters, context, many):
        if "jarvis.policies" in statement and "FOR UPDATE" in statement:
            control_attempt.wait()

    def control():
        with control_engine.begin() as connection:
            connection.execute(
                select(Policy).where(Policy.owner_id == normal.owner_id).with_for_update()
            )
            # Visibility here proves the writer committed before the control acquired its guard.
            claim = connection.execute(select(ClaimRecord)).mappings().one()
            assert claim["policy_revision"] == 0
            connection.execute(
                update(Policy).where(Policy.owner_id == normal.owner_id).values(revision=1)
            )
            return claim["id"]

    event.listen(writer_engine, "after_cursor_execute", after_writer_lock)
    event.listen(control_engine, "before_cursor_execute", before_control_lock)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(Service(writer_engine).commit_claim, normal, proposal)
            writer_locked.wait()
            controller = pool.submit(control)
            control_attempt.wait()
            assert not controller.done()
            release_writer.wait()
            saved = writer.result(timeout=10)
            assert controller.result(timeout=10) == saved.id
    finally:
        event.remove(writer_engine, "after_cursor_execute", after_writer_lock)
        event.remove(control_engine, "before_cursor_execute", before_control_lock)
        writer_engine.dispose()
        control_engine.dispose()


def test_competing_claim_revisions_cannot_both_commit(service, normal, proposal, settings, engine):
    first = service.commit_claim(normal, proposal)
    proposal.update(claim_id=str(first.claim_id), expected_claim_revision=1)
    start = Barrier(2, timeout=10)

    def write():
        independent = make_engine(settings)
        try:
            start.wait()
            try:
                return Service(independent).commit_claim(normal, deepcopy(proposal)).revision
            except ApplicationError as error:
                return error.code
        finally:
            independent.dispose()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: write(), range(2)))
    assert sorted(map(str, outcomes)) == ["2", ErrorCode.STALE_REVISION.value]
    with engine.connect() as connection:
        assert len(connection.execute(select(ClaimRecord)).all()) == 2
