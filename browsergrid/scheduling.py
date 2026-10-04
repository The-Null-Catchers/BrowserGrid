from datetime import timedelta, timezone
from sqlalchemy import func, select
from browsergrid.config import settings
from browsergrid.lifecycle import ACTIVE, TERMINAL, transition
from browsergrid.models import Job, Run, Worker, Workspace, now, uid


# Database is the durable queue. Redis only provides wake-up notifications.
def acquire(db, worker_id):
    # Skip busy workspace locks: independent tenants can schedule concurrently.
    workspaces = db.scalars(
        select(Workspace).order_by(Workspace.created_at).with_for_update(skip_locked=True)
    ).all()
    worker = db.scalar(select(Worker).where(Worker.id == worker_id).with_for_update())
    if not worker:
        worker = Worker(id=worker_id, version=settings().worker_version)
        db.add(worker)
    worker.heartbeat_at = now()
    if worker.job_id:
        current = db.get(Job, worker.job_id)
        if current and current.status in ACTIVE:
            db.commit()
            return None
        worker.job_id = None
    for workspace in workspaces:
        active = db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.workspace_id == workspace.id, Job.status.in_(ACTIVE))
        )
        if active >= workspace.concurrency:
            continue
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
    # Same workspace locking order as acquire, cancellation, and worker writes.
    for workspace in db.scalars(
        select(Workspace).order_by(Workspace.created_at).with_for_update(skip_locked=True)
    ):
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
            transition(db, job, status, "RUN_TIMEOUT" if timed_out else "WORKER_LOST")
            job.lease_token = None
            worker = db.get(Worker, job.worker_id)
            if worker and worker.job_id == job.id:
                worker.job_id = None
    db.commit()


def leased_job(db, job_id, token):
    job = db.get(Job, job_id)
    if not job:
        raise RuntimeError("Unknown job")
    db.scalar(select(Workspace).where(Workspace.id == job.workspace_id).with_for_update())
    db.refresh(job)
    if job.lease_token != token or job.status in TERMINAL:
        raise RuntimeError("Execution lease no longer valid")
    return job
