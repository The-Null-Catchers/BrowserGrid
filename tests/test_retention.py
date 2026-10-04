from datetime import timedelta
import threading
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from browsergrid import scheduler
from browsergrid.models import Artifact, now
from tests.test_worker import prepare


def test_unavailable_object_does_not_block_other_expired_artifacts(db, monkeypatch):
    rid, jid, _ = prepare(db, monkeypatch)
    for aid in ("bad", "good", "not-expired"):
        db.add(
            Artifact(
                id=aid,
                run_id=rid,
                job_id=jid,
                key=aid,
                name=aid,
                kind="log",
                size=1,
                mime="text/plain",
                expires_at=now() + timedelta(days=1 if aid == "not-expired" else -1),
            )
        )
    db.commit()
    deleted = []

    def delete(key):
        if key == "bad":
            raise OSError("object-specific storage error")
        deleted.append(key)

    monkeypatch.setattr(scheduler.storage, "delete", delete)
    scheduler.cleanup(db)
    assert deleted == ["good"]
    assert set(db.scalars(select(Artifact.id))) == {"bad", "not-expired"}


def test_stalled_retention_does_not_delay_recovery(db, monkeypatch):
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(scheduler, "session_factory", lambda: factory)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    stop = threading.Event()
    recovered = []

    def stalled(db):
        entered.set()
        try:
            assert release.wait(5)
        finally:
            finished.set()

    def recovery(db):
        assert entered.wait(1)
        recovered.append(True)
        stop.set()

    monkeypatch.setattr(scheduler, "cleanup", stalled)
    monkeypatch.setattr(scheduler, "recover", recovery)
    try:
        scheduler.run(stop)
        assert recovered == [True]
        assert not finished.is_set(), "recovery waited for retention to finish"
    finally:
        release.set()
        assert finished.wait(1)
