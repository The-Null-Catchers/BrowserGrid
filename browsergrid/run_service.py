import json
from sqlalchemy import func, select
from browsergrid.config import settings
from browsergrid.models import Bundle, Event, Job, Run, Workspace, now
from browsergrid.security import digest


class RunCreationError(Exception):
    def __init__(self, status, detail):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def enqueue_run(db, project, p, data, idempotency_key):
    config = data.config.model_dump()
    if len(config["browsers"]) * len(config["viewports"]) > settings().max_run_jobs:
        raise RunCreationError(422, "Matrix exceeds job limit")
    if config["source"]["type"] == "bundle":
        bundle = db.get(Bundle, config["source"]["bundle_id"])
        if not bundle or bundle.project_id != project.id:
            raise RunCreationError(404, "Bundle not found")
    request_hash = digest(json.dumps(data.model_dump(), sort_keys=True))
    if idempotency_key and len(idempotency_key) > 128:
        raise RunCreationError(422, "Idempotency key too long")
    # Lock the same workspace row used by job acquisition and quota counting.
    workspace = db.scalar(
        select(Workspace).where(Workspace.id == project.workspace_id).with_for_update()
    )
    if idempotency_key:
        existing = db.scalar(
            select(Run).where(
                Run.workspace_id == workspace.id, Run.idempotency_key == idempotency_key
            )
        )
        if existing:
            if existing.request_hash != request_hash:
                raise RunCreationError(409, "Idempotency key payload differs")
            db.commit()
            return {"id": existing.id, "status": existing.status}
    midnight = now().replace(hour=0, minute=0, second=0, microsecond=0)
    count = db.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.workspace_id == workspace.id, Job.created_at >= midnight)
    )
    jobs = len(config["browsers"]) * len(config["viewports"])
    if count + jobs > min(workspace.daily_jobs, settings().max_daily_jobs):
        raise RunCreationError(429, "Workspace daily execution quota exceeded")
    run = Run(
        project_id=project.id,
        workspace_id=workspace.id,
        actor_id=p.user_id,
        config=config,
        request_hash=request_hash,
        idempotency_key=idempotency_key,
        trigger="API" if p.key else "manual",
    )
    db.add(run)
    db.flush()
    for browser in config["browsers"]:
        for viewport in config["viewports"]:
            job = Job(run_id=run.id, workspace_id=workspace.id, browser=browser, viewport=viewport)
            db.add(job)
            db.flush()
            db.add(Event(run_id=run.id, job_id=job.id, kind="state", data={"state": "queued"}))
    db.commit()
    return {"id": run.id, "status": run.status}
