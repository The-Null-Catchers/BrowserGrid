"""Required contention test; skipped locally when no PostgreSQL service is available."""

import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from browsergrid.db import Base
from browsergrid.models import Job
from browsergrid.scheduling import acquire
from tests.test_scheduler import seed


@pytest.mark.skipif(
    not os.environ.get("BG_TEST_DATABASE_URL"), reason="PostgreSQL service required"
)
def test_postgres_workspace_concurrency_is_atomic():
    engine = create_engine(os.environ["BG_TEST_DATABASE_URL"])
    factory = sessionmaker(engine, expire_on_commit=False)
    # Dedicated ephemeral CI database only. Never point this variable at production.
    Base.metadata.create_all(engine)
    try:
        with factory() as db:
            run = seed(db, n=6, concurrency=1)
            rid = run.id

        def claim(index):
            with factory() as db:
                return acquire(db, f"contention-worker-{index}")

        with ThreadPoolExecutor(max_workers=6) as executor:
            claims = list(executor.map(claim, range(6)))
        assert sum(claim is not None for claim in claims) == 1
        with factory() as db:
            jobs = db.scalars(select(Job).where(Job.run_id == rid)).all()
            assert sum(j.status == "preparing" for j in jobs) == 1
            assert sum(j.status == "queued" for j in jobs) == 5
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
