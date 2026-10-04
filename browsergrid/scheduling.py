from datetime import timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from browsergrid.config import settings
from browsergrid.lifecycle import ACTIVE, transition
from browsergrid.models import Job, Run, Worker, Workspace, now, uid


# Database is the durable queue. Redis only provides wake-up notifications.
def acquire(db, worker_id):
    # Lock only one eligible tenant; ordering follows the oldest queued job.
    oldest = (
        select(func.min(Job.created_at))
        .join(Run)
        .where(
            Job.workspace_id == Workspace.id,
            Job.status == "queued",
            Run.cancel_requested.is_(False),
        )
        .correlate(Workspace)
        .scalar_subquery()
    )
    active_count = (
        select(func.count())
        .select_from(Job)
        .where(Job.workspace_id == Workspace.id, Job.status.in_(ACTIVE))
        .correlate(Workspace)
        .scalar_subquery()
    )
    workspace = db.scalar(
        select(Workspace)
        .where(oldest.is_not(None), active_count < Workspace.concurrency)
        .order_by(oldest, Workspace.created_at, Workspace.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    worker = db.scalar(select(Worker).where(Worker.id == worker_id).with_for_update())
    if not worker:
        # Two processes may register the same ID before either commits. A savepoint
        # handles the unique-key race without losing the workspace lock/transaction.
        try:
            with db.begin_nested():
                worker = Worker(id=worker_id, version=settings().worker_version)
                db.add(worker)
                db.flush()
        except IntegrityError:
            worker = db.scalar(select(Worker).where(Worker.id == worker_id).with_for_update())
            if worker is None:
                raise
    worker.heartbeat_at = now()
    if worker.job_id:
        current = db.get(Job, worker.job_id)
        if current and current.status in ACTIVE:
            db.commit()
            return None
        worker.job_id = None
    if workspace:
        active = db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.workspace_id == workspace.id, Job.status.in_(ACTIVE))
        )
        if active >= workspace.concurrency:
            db.commit()
            return None
        job = db.scalar(
            select(Job)
            .join(Run)
            .where(
                Job.workspace_id == workspace.id,
                Job.status == "queued",
                Run.cancel_requested.is_(False),
            )
            .order_by(Job.created_at, Job.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job:
            job.worker_id = worker_id
            job.lease_token = uid()
            job.heartbeat_at = now()
            worker.job_id = job.id
            transition(db, job, "preparing")
            db.commit()
            return job.id, job.lease_token
    db.commit()
    return None


def heartbeat(db, worker_id, job_id=None, token=None):
    if job_id:
        # Keep the same workspace -> job -> worker lock order as recovery/results.
        # Updating the worker first could deadlock against recovery's job update.
        try:
            job = leased_job(db, job_id, token)
        except RuntimeError:
            db.rollback()
            return False
        if job.worker_id != worker_id:
            db.rollback()
            return False
        job.heartbeat_at = now()
        cancelled = db.get(Run, job.run_id).cancel_requested
    else:
        cancelled = False
    worker = db.get(Worker, worker_id)
    if worker:
        worker.heartbeat_at = now()
    db.commit()
    return not cancelled


def recover(db):
    clock = now()
    cutoff = clock - timedelta(seconds=settings().lease_seconds)
    # Recover one tenant per transaction, with the same lock order as worker writes.
    # Empty tenants need no locks; a large sweep must not hold unrelated tenants.
    workspace_ids = db.scalars(
        select(Workspace.id)
        .where(
            select(Job.id).where(Job.workspace_id == Workspace.id, Job.status.in_(ACTIVE)).exists()
        )
        .order_by(Workspace.created_at, Workspace.id)
    ).all()
    for workspace_id in workspace_ids:
        workspace = db.scalar(
            select(Workspace).where(Workspace.id == workspace_id).with_for_update(skip_locked=True)
        )
        if workspace is None:
            db.rollback()
            continue
        jobs = db.scalars(
            select(Job)
            .where(Job.workspace_id == workspace.id, Job.status.in_(ACTIVE))
            .with_for_update(skip_locked=True)
        ).all()
        for job in jobs:
            run = db.get(Run, job.run_id)
            started = job.started_at
            heartbeat_at = job.heartbeat_at
            if started and started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if heartbeat_at and heartbeat_at.tzinfo is None:
                heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)
            timed_out = started and clock >= started + timedelta(
                seconds=run.config.get("timeout_seconds", 900)
            )
            stale = heartbeat_at is None or heartbeat_at < cutoff
            if not timed_out and not stale:
                continue
            status = (
                "cancelled"
                if run.cancel_requested
                else "timed_out"
                if timed_out
                else "infrastructure_failed"
            )
            error = None if status == "cancelled" else "RUN_TIMEOUT" if timed_out else "WORKER_LOST"
            transition(db, job, status, error)
            job.lease_token = None
            worker = db.get(Worker, job.worker_id)
            if worker and worker.job_id == job.id:
                worker.job_id = None
        db.commit()
    db.commit()


def leased_job(db, job_id, token):
    job = db.get(Job, job_id)
    if not job:
        raise RuntimeError("Unknown job")
    db.scalar(select(Workspace).where(Workspace.id == job.workspace_id).with_for_update())
    db.refresh(job)
    if not token or not job.lease_token or job.lease_token != token or job.status not in ACTIVE:
        raise RuntimeError("Execution lease no longer valid")
    return job
