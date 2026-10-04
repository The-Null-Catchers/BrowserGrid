from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
import pytest
from browsergrid import bundles, scheduler, storage
from browsergrid.models import Bundle, Member, Run, now
from tests.test_security import archive


def source_zip():
    return archive(
        {"package.json": "{}", "package-lock.json": "{}", "tests/basic.spec.ts": "test()"}
    )


def upload(client, project, data=None):
    return client.post(
        f"/api/v1/projects/{project['id']}/bundles",
        files={"file": ("suite.zip", source_zip() if data is None else data, "application/zip")},
    )


def run_payload(project, bid):
    return {"project_id": project["id"], "config": {"source": {"type": "bundle", "bundle_id": bid}}}


def test_reservation_exists_before_object_write(client, account, db, monkeypatch):
    _, project = account
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    observed = []

    def put(key, data, mime):
        with factory() as other:
            reservation = other.scalar(select(Bundle).where(Bundle.key == key))
            assert reservation is not None and not reservation.ready
            assert reservation.expires_at is not None
            assert mime == "application/zip" and data == source_zip()
            observed.append(reservation.id)

    monkeypatch.setattr(storage, "put", put)
    response = upload(client, project)
    assert response.status_code == 201, response.text
    assert response.json()["id"] == observed[0]
    db.expire_all()
    bundle = db.get(Bundle, observed[0])
    assert bundle.ready and bundle.expires_at is None
    assert client.post("/api/v1/runs", json=run_payload(project, bundle.id)).status_code == 201


def test_lost_upload_response_remains_hidden_and_cleanupable(client, account, db, monkeypatch):
    _, project = account

    def lost_response(*args):
        raise OSError("storage credentials must not appear in the response")

    monkeypatch.setattr(storage, "put", lost_response)
    response = upload(client, project)
    assert response.status_code == 503
    assert "credentials" not in response.text
    db.expire_all()
    bundle = db.scalar(select(Bundle))
    assert bundle is not None and not bundle.ready
    assert client.post("/api/v1/runs", json=run_payload(project, bundle.id)).status_code == 404
    assert not list(db.scalars(select(Run)))
    bundle.expires_at = now() - timedelta(seconds=1)
    db.commit()
    deleted = []
    monkeypatch.setattr(storage, "delete", deleted.append)
    scheduler.cleanup(db)
    assert deleted == [bundle.key]
    assert db.get(Bundle, bundle.id) is None


def test_expired_upload_completion_is_rejected(client, account, db, monkeypatch):
    _, project = account
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)

    def delayed_write(key, *args):
        with factory() as other:
            reservation = other.scalar(select(Bundle).where(Bundle.key == key))
            reservation.expires_at = now() - timedelta(seconds=1)
            other.commit()

    monkeypatch.setattr(storage, "put", delayed_write)
    response = upload(client, project)
    assert response.status_code == 409
    db.expire_all()
    assert not db.scalar(select(Bundle)).ready


def test_invalid_archive_does_not_reserve_or_upload(client, account, db, monkeypatch):
    _, project = account
    written = []
    monkeypatch.setattr(storage, "put", lambda *args: written.append(args))
    assert upload(client, project, b"invalid ZIP").status_code == 422
    assert not written
    assert not list(db.scalars(select(Bundle)))


def test_viewer_cannot_upload(client, account, db, monkeypatch):
    workspace, project = account
    member = db.scalar(select(Member).where(Member.workspace_id == workspace["id"]))
    member.role = "viewer"
    db.commit()
    written = []
    monkeypatch.setattr(storage, "put", lambda *args: written.append(args))
    assert upload(client, project).status_code == 403
    assert not written and not list(db.scalars(select(Bundle)))


def test_bundle_from_another_project_cannot_be_used(client, account, db, monkeypatch):
    workspace, project = account
    monkeypatch.setattr(storage, "put", lambda *args: None)
    bid = upload(client, project).json()["id"]
    other_project = client.post(
        f"/api/v1/workspaces/{workspace['id']}/projects", json={"name": "Other"}
    ).json()
    assert client.post("/api/v1/runs", json=run_payload(other_project, bid)).status_code == 404


def test_failed_pending_delete_is_retried_without_deleting_ready_source(
    client, account, db, monkeypatch
):
    _, project = account
    bad = bundles.reserve(db, project["id"], 1)
    good = bundles.reserve(db, project["id"], 1)
    ready = bundles.complete(db, bundles.reserve(db, project["id"], 1).id)
    for bundle in (bad, good, ready):
        bundle.expires_at = now() - timedelta(seconds=1)
    db.commit()
    deleted = []

    def delete(key):
        if key == bad.key:
            raise OSError("object-specific failure")
        deleted.append(key)

    monkeypatch.setattr(storage, "delete", delete)
    scheduler.cleanup(db)
    assert deleted == [good.key]
    assert db.get(Bundle, bad.id) and db.get(Bundle, ready.id)
    assert db.get(Bundle, good.id) is None
    monkeypatch.setattr(storage, "delete", deleted.append)
    scheduler.cleanup(db)
    assert db.get(Bundle, bad.id) is None
    assert db.get(Bundle, ready.id).ready


def test_removed_reservation_cannot_be_completed(client, account, db):
    _, project = account
    bundle = bundles.reserve(db, project["id"], 1)
    db.delete(bundle)
    db.commit()
    with pytest.raises(bundles.BundleUploadExpired):
        bundles.complete(db, bundle.id)


def test_cross_workspace_upload_is_denied_before_storage(client, account, db, monkeypatch):
    _, project = account
    client.post("/api/v1/auth/logout", json={})
    client.post(
        "/api/v1/auth/register",
        json={"email": "stranger@example.test", "password": "different-password-123"},
    )
    written = []
    monkeypatch.setattr(storage, "put", lambda *args: written.append(args))
    assert upload(client, project).status_code == 404
    assert not written and not list(db.scalars(select(Bundle)))


def test_read_only_api_key_cannot_upload(client, account, db, monkeypatch):
    workspace, project = account
    key = client.post(
        f"/api/v1/workspaces/{workspace['id']}/api-keys",
        json={"name": "Reader", "scopes": ["runs:read"]},
    ).json()
    written = []
    monkeypatch.setattr(storage, "put", lambda *args: written.append(args))
    response = client.post(
        f"/api/v1/projects/{project['id']}/bundles",
        headers={"Authorization": "Bearer " + key["token"]},
        files={"file": ("suite.zip", source_zip(), "application/zip")},
    )
    assert response.status_code == 403, response.text
    assert not written and not list(db.scalars(select(Bundle)))
