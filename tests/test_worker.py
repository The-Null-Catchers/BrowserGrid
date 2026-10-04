"""Worker lifecycle unit tests. Real Docker/browser acceptance remains a separate CI job."""

import json
from sqlalchemy.orm import sessionmaker
from browsergrid.models import Job, Run
from browsergrid.scheduling import acquire
from browsergrid.worker import execute
from tests.test_scheduler import seed


class Container:
    def __init__(self, states, exit_code):
        self.lines = [
            (b"@bg:" + json.dumps({"kind": "state", "state": state}).encode() + b"\n")
            for state in states
        ]
        self.lines.append(
            b"@bg:" + json.dumps({"kind": "completed", "exit_code": exit_code}).encode() + b"\n"
        )

    def logs(self, **kwargs):
        return iter(self.lines)


class Backend:
    def __init__(self, outcome="expected", setup_failure=False):
        self.stopped = False
        self.collected = False
        states = ["installing_dependencies", "starting_browser"] + (
            [] if setup_failure else ["running"]
        )
        self.container = Container(states, 2 if setup_failure else 0)
        self.report = json.dumps(
            {
                "suites": [
                    {
                        "title": "suite",
                        "specs": [
                            {
                                "title": "test",
                                "tests": [
                                    {
                                        "status": outcome,
                                        "results": [
                                            {
                                                "status": "passed"
                                                if outcome == "expected"
                                                else "failed",
                                                "duration": 5,
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ).encode()

    def create(self, spec):
        assert not self.stopped
        return self.container

    def status(self, container):
        return {"Running": True, "ExitCode": None}

    def artifacts(self, container):
        assert not self.stopped, "tmpfs must be collected before sandbox removal"
        self.collected = True
        return {"report.json": self.report, "test.png": b"unit-test-artifact"}

    def stop(self, container):
        self.stopped = True


def prepare(db, monkeypatch):
    import browsergrid.worker as worker

    run = seed(db, n=1)
    run.config = {
        "source": {"type": "inline", "code": "unit-test-input"},
        "timeout_seconds": 10,
        "retention_days": 7,
        "env": {},
    }
    db.commit()
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(worker, "session_factory", lambda: factory)
    monkeypatch.setattr(worker.storage, "put", lambda *args: None)
    jid, token = acquire(db, "worker-unit")
    return run.id, jid, token


def test_worker_success_collects_before_destroy(db, monkeypatch):
    rid, jid, token = prepare(db, monkeypatch)
    backend = Backend()
    execute(backend, "worker-unit", jid, token)
    db.expire_all()
    assert db.get(Run, rid).status == "passed"
    assert backend.collected and backend.stopped


def test_worker_report_failure_cannot_pass_with_zero_exit(db, monkeypatch):
    rid, jid, token = prepare(db, monkeypatch)
    backend = Backend("unexpected")
    execute(backend, "worker-unit", jid, token)
    db.expire_all()
    assert db.get(Run, rid).status == "failed"
    assert db.get(Job, jid).error_code == "TEST_FAILED"
    assert backend.stopped


def test_browser_setup_failure_is_infrastructure_failure(db, monkeypatch):
    rid, jid, token = prepare(db, monkeypatch)
    backend = Backend(setup_failure=True)
    execute(backend, "worker-unit", jid, token)
    db.expire_all()
    assert db.get(Run, rid).status == "infrastructure_failed"
    assert db.get(Job, jid).error_code == "RUNTIME_SETUP_FAILED"
    assert not backend.collected and backend.stopped


def test_upload_failure_is_not_test_failure(db, monkeypatch):
    import browsergrid.worker as worker

    rid, jid, token = prepare(db, monkeypatch)

    def unavailable(*args):
        raise OSError("test object service failure")

    monkeypatch.setattr(worker.storage, "put", unavailable)
    backend = Backend()
    execute(backend, "worker-unit", jid, token)
    db.expire_all()
    assert db.get(Run, rid).status == "infrastructure_failed"
    assert backend.stopped
