from datetime import timedelta
import pytest
from browsergrid.lifecycle import transition
from browsergrid.models import Job, Member, Project, Run, User, Worker, Workspace, now
from browsergrid.scheduling import acquire, heartbeat, leased_job, recover


def seed(db, n=4, concurrency=2):
    user = User(email="worker@example.test", password_hash="not-used")
    workspace = Workspace(name="Scheduling", concurrency=concurrency)
    db.add_all([user, workspace])
    db.flush()
    db.add(Member(workspace_id=workspace.id, user_id=user.id, role="owner"))
    project = Project(workspace_id=workspace.id, name="Fixture")
    db.add(project)
    db.flush()
    run = Run(
        project_id=project.id,
        workspace_id=workspace.id,
        actor_id=user.id,
        config={},
        request_hash="x",
    )
    db.add(run)
    db.flush()
    for _ in range(n):
        db.add(Job(run_id=run.id, workspace_id=workspace.id, browser="chromium", viewport={}))
    db.commit()
    return run


def test_acquisition_respects_workspace_concurrency(db):
    seed(db)
    first = acquire(db, "w1")
    second = acquire(db, "w2")
    assert first and second and first[0] != second[0]
    assert acquire(db, "w3") is None
    job = db.get(Job, first[0])
    transition(db, job, "infrastructure_failed", "TEST_WORKER_FAILURE")
    db.commit()
    assert acquire(db, "w3")


def test_heartbeat_loss_fences_worker(db):
    run = seed(db, n=1)
    jid, token = acquire(db, "w1")
    job = db.get(Job, jid)
    job.heartbeat_at = now() - timedelta(minutes=2)
    db.commit()
    recover(db)
    assert job.status == "infrastructure_failed"
    assert job.error_code == "WORKER_LOST"
    assert db.get(Run, run.id).status == "infrastructure_failed"
    assert db.get(Worker, "w1").job_id is None
    with pytest.raises(RuntimeError, match="lease"):
        leased_job(db, jid, token)
    assert not heartbeat(db, "w1", jid, token)


def test_cancel_requested_reaches_worker(db):
    run = seed(db, n=1)
    jid, token = acquire(db, "w1")
    run.cancel_requested = True
    db.commit()
    assert not heartbeat(db, "w1", jid, token)


def test_invalid_terminal_transition(db):
    seed(db, n=1)
    jid, _ = acquire(db, "w1")
    job = db.get(Job, jid)
    transition(db, job, "cancelled")
    with pytest.raises(ValueError):
        transition(db, job, "running")


def test_scheduler_expires_wall_deadline_with_fresh_heartbeat(db):
    run = seed(db, n=1)
    run.config = {"timeout_seconds": 10}
    db.commit()
    jid, token = acquire(db, "w1")
    job = db.get(Job, jid)
    job.started_at = now() - timedelta(seconds=20)
    job.heartbeat_at = now()
    db.commit()
    recover(db)
    assert job.status == "timed_out"
    assert job.error_code == "RUN_TIMEOUT"
    assert job.lease_token is None
    with pytest.raises(RuntimeError):
        leased_job(db, jid, token)
