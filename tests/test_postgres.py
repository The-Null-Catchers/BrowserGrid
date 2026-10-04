"""Real PostgreSQL locking tests; each test owns a disposable, isolated schema."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema
from browsergrid.db import Base
from browsergrid.lifecycle import transition
from browsergrid.models import Job, Run, User, Worker, Workspace, now
from browsergrid.scheduling import acquire, heartbeat, leased_job, recover
from tests.test_scheduler import seed

pytestmark = pytest.mark.skipif(
    not os.environ.get("BG_TEST_DATABASE_URL"), reason="PostgreSQL service required"
)


@pytest.fixture
def pg():
    # Use a dedicated CI database. Never drop application tables or unrelated schemas.
    engine = create_engine(
        os.environ["BG_TEST_DATABASE_URL"],
        connect_args={"options": "-c statement_timeout=10000 -c lock_timeout=5000"},
    )
    schema = "bg_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    factory = sessionmaker(isolated, expire_on_commit=False)
    try:
        Base.metadata.create_all(isolated)
        yield factory
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def test_postgres_workspace_concurrency_is_atomic(pg):
    with pg() as db:
        run = seed(db, n=6, concurrency=1)
        rid = run.id
    barrier = threading.Barrier(6)

    def claim(index):
        barrier.wait(timeout=5)
        with pg() as db:
            return acquire(db, f"contention-worker-{index}")

    with ThreadPoolExecutor(max_workers=6) as executor:
        claims = list(executor.map(claim, range(6)))
    assert sum(claim is not None for claim in claims) == 1
    with pg() as db:
        jobs = db.scalars(select(Job).where(Job.run_id == rid)).all()
        assert sum(j.status == "preparing" for j in jobs) == 1
        assert sum(j.status == "queued" for j in jobs) == 5


def seed_tenants(pg):
    with pg() as db:
        first = seed(db, n=2, concurrency=1)
        db.get(User, first.actor_id).email = "first-tenant@example.test"
        db.commit()
        second = seed(db, n=2, concurrency=1)
        return first.id, first.workspace_id, second.id, second.workspace_id


def test_locked_workspace_does_not_block_another_tenant(pg):
    first, wid, second, _ = seed_tenants(pg)
    with pg() as held, pg() as other:
        held.scalar(select(Workspace).where(Workspace.id == wid).with_for_update())
        claimed = acquire(other, "independent-worker")
        assert claimed
        assert other.get(Job, claimed[0]).run_id == second
        assert other.scalar(select(Job.status).where(Job.run_id == first).limit(1)) == "queued"
        held.rollback()


def test_acquisition_locks_only_assigned_workspace(pg):
    _, _, _, other_wid = seed_tenants(pg)
    with pg() as claiming, pg() as observer:
        # Inspect lock scope before commit releases the acquisition transaction.
        original_commit = claiming.commit
        claiming.commit = lambda: None
        try:
            assert acquire(claiming, "scoped-worker")
            row = observer.scalar(
                select(Workspace).where(Workspace.id == other_wid).with_for_update(nowait=True)
            )
            assert row is not None
        finally:
            claiming.commit = original_commit
            claiming.rollback()
            observer.rollback()


def test_duplicate_worker_registration_cannot_claim_twice(pg):
    with pg() as db:
        seed(db, n=4, concurrency=4)
    barrier = threading.Barrier(2)

    def claim(_):
        barrier.wait(timeout=5)
        with pg() as db:
            return acquire(db, "shared-worker-id")

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, range(2)))
    assert sum(claim is not None for claim in claims) == 1
    with pg() as db:
        worker = db.get(Worker, "shared-worker-id")
        assert worker.job_id == next(claim[0] for claim in claims if claim)
        assert len(db.scalars(select(Job).where(Job.status == "preparing")).all()) == 1


def test_recovery_fences_an_old_session_before_it_can_write(pg):
    with pg() as db:
        run = seed(db, n=1)
        rid = run.id
        jid, token = acquire(db, "lost-worker")
        db.get(Job, jid).heartbeat_at = now() - timedelta(minutes=2)
        db.commit()
    with pg() as stale, pg() as recovery:
        # Cache a valid-looking entity before another session fences it.
        cached = stale.get(Job, jid)
        assert cached.lease_token == token
        recover(recovery)
        with pytest.raises(RuntimeError, match="lease"):
            leased_job(stale, jid, token)
        stale.rollback()
        assert not heartbeat(stale, "lost-worker", jid, token)
    with pg() as db:
        assert db.get(Job, jid).status == "infrastructure_failed"
        assert db.get(Run, rid).status == "infrastructure_failed"


def test_oldest_job_selected_across_workspace_creation_order(pg):
    first, _, second, _ = seed_tenants(pg)
    with pg() as db:
        older = db.scalar(select(Job).where(Job.run_id == second).limit(1))
        older.created_at = now() - timedelta(minutes=2)
        db.commit()
        claimed = acquire(db, "ordered-worker")
        assert claimed[0] == older.id
        transition(db, leased_job(db, *claimed), "cancelled")
        db.commit()
        assert db.scalar(select(Job.status).where(Job.run_id == first).limit(1)) == "queued"


def test_recovery_does_not_lock_all_tenants_at_once(pg, monkeypatch):
    import browsergrid.scheduling as scheduling

    first, _, second, other_wid = seed_tenants(pg)
    with pg() as db:
        for worker in ("first-worker", "second-worker"):
            jid, _ = acquire(db, worker)
            db.get(Job, jid).heartbeat_at = now() - timedelta(minutes=2)
            db.commit()
    observed = []
    original = scheduling.transition

    def inspect_scope(db, job, status, error=None):
        if job.run_id == first:
            with pg() as observer:
                row = observer.scalar(
                    select(Workspace).where(Workspace.id == other_wid).with_for_update(nowait=True)
                )
                observed.append(row is not None)
        original(db, job, status, error)

    monkeypatch.setattr(scheduling, "transition", inspect_scope)
    with pg() as db:
        recover(db)
        assert observed == [True]
        for rid in (first, second):
            states = list(db.scalars(select(Job.status).where(Job.run_id == rid)))
            assert states.count("infrastructure_failed") == 1
            assert states.count("queued") == 1
        assert db.get(Worker, "first-worker").job_id is None
        assert db.get(Worker, "second-worker").job_id is None
