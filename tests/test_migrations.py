from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from browsergrid.config import settings


def test_artifact_reservation_migration_preserves_existing_downloads(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "upgrade.db")
    monkeypatch.setattr(settings(), "database_url", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "0001")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO artifacts(id,run_id,job_id,key,name,kind,size,mime,created_at) VALUES ('legacy','r','j','legacy/key','shot.png','screenshot',1,'image/png','2026-10-04 00:00:00')"
            )
        )
    command.upgrade(config, "head")
    with engine.connect() as db:
        assert db.scalar(text("SELECT ready FROM artifacts WHERE id='legacy'")) == 1
    command.downgrade(config, "0001")
    assert "ready" not in {c["name"] for c in inspect(engine).get_columns("artifacts")}
    command.downgrade(config, "base")
    assert "artifacts" not in inspect(engine).get_table_names()
    engine.dispose()
