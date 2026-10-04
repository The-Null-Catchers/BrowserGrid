import logging
import time
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
        storage.delete(artifact.key)
        db.delete(artifact)
    db.commit()


def main():
    logging.basicConfig(level=logging.INFO)
    tick = 0
    while True:
        try:
            with session_factory()() as db:
                recover(db)
            if tick % 12 == 0:
                with session_factory()() as db:
                    cleanup(db)
        except Exception:
            log.exception("Scheduler sweep failed")
        tick += 1
        time.sleep(5)


if __name__ == "__main__":
    main()
