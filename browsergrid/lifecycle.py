from sqlalchemy import select
from browsergrid.models import Event, Job, Run, now

TERMINAL = {"passed", "failed", "cancelled", "timed_out", "infrastructure_failed"}
ACTIVE = {
    "preparing",
    "pulling_source",
    "installing_dependencies",
    "starting_browser",
    "running",
    "uploading_artifacts",
}
TRANSITIONS = {
    "queued": {"preparing", "cancelled"},
    "preparing": {
        "pulling_source",
        "installing_dependencies",
        "starting_browser",
        "infrastructure_failed",
        "timed_out",
        "cancelled",
    },
    "pulling_source": {
        "installing_dependencies",
        "infrastructure_failed",
        "timed_out",
        "cancelled",
    },
    "installing_dependencies": {
        "starting_browser",
        "infrastructure_failed",
        "timed_out",
        "cancelled",
    },
    "starting_browser": {"running", "infrastructure_failed", "timed_out", "cancelled"},
    "running": {"uploading_artifacts", "infrastructure_failed", "timed_out", "cancelled"},
    "uploading_artifacts": TERMINAL,
}


def event(db, job, kind, data):
    db.add(Event(run_id=job.run_id, job_id=job.id, kind=kind, data=data))


def transition(db, job, status, error=None):
    if status not in TRANSITIONS.get(job.status, set()):
        raise ValueError(f"Invalid transition {job.status} -> {status}")
    old = job.status
    job.status = status
    if status == "preparing":
        job.started_at = now()
    if status in TERMINAL:
        job.finished_at = now()
    job.error_code = error
    event(db, job, "state", {"from": old, "state": status, "error_code": error})
    db.flush()
    aggregate(db, job.run_id)


def aggregate(db, run_id):
    run = db.get(Run, run_id)
    states = list(db.scalars(select(Job.status).where(Job.run_id == run_id)))
    if not states:
        return
    if all(s in TERMINAL for s in states):
        run.status = next(
            (
                s
                for s in ["cancelled", "infrastructure_failed", "timed_out", "failed"]
                if s in states
            ),
            "passed",
        )
        run.finished_at = now()
    elif any(s in ACTIVE for s in states):
        run.status = "running"
    else:
        run.status = "queued"
