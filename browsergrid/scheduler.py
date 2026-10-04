import logging
import signal
import threading
from sqlalchemy import select
from browsergrid import storage
from browsergrid.db import session_factory
from browsergrid.models import Artifact, now
from browsergrid.scheduling import recover

log = logging.getLogger("browsergrid.scheduler")


def cleanup(db):
    for artifact in db.scalars(
        select(Artifact)
        .where(Artifact.expires_at < now())
        .order_by(Artifact.expires_at)
        .limit(100)
        .with_for_update(skip_locked=True)
    ):
        # Delete object before metadata; failures are retried next sweep.
        try:
            storage.delete(artifact.key)
        except Exception:
            log.exception("Artifact deletion failed artifact_id=%s", artifact.id)
            continue
        db.delete(artifact)
    db.commit()


def retention_loop(stop):
    while not stop.is_set():
        try:
            with session_factory()() as db:
                cleanup(db)
        except Exception:
            log.exception("Artifact retention sweep failed")
        stop.wait(60)


def run(stop):
    # Object-store latency must never delay stale-lease recovery or job timeouts.
    retention = threading.Thread(target=retention_loop, args=(stop,), daemon=True)
    retention.start()
    try:
        while not stop.is_set():
            try:
                with session_factory()() as db:
                    recover(db)
            except Exception:
                log.exception("Scheduler recovery sweep failed")
            stop.wait(5)
    finally:
        stop.set()
        retention.join(timeout=1)


def main():
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    run(stop)


if __name__ == "__main__":
    main()
