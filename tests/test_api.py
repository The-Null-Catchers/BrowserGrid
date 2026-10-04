from sqlalchemy import select
from browsergrid.models import ApiKey, Event, Job, Member, Run, Secret, Session
from browsergrid.security import digest

CODE = 'import {test} from "@playwright/test";test("smoke",async()=>{});'


def payload(project, browsers=None):
    return {
        "project_id": project["id"],
        "config": {
            "source": {"type": "inline", "code": CODE},
            "browsers": browsers or ["chromium"],
        },
    }


def test_session_hashed_logout_revokes(client, account, db):
    token = client.cookies.get("bg_session")
    assert db.get(Session, digest(token))
    assert token not in str(list(db.scalars(select(Session.digest))))
    assert client.post("/api/v1/auth/logout", json={}).status_code == 204
    assert db.get(Session, digest(token)) is None
    assert client.get("/api/v1/me").status_code == 401


def test_session_mutation_origin_required(client, account):
    assert (
        client.post(
            "/api/v1/workspaces",
            headers={"Origin": "https://attacker.test"},
            json={"name": "unsafe"},
        ).status_code
        == 403
    )


def test_idempotency_and_matrix(client, account, db):
    _, project = account
    body = payload(project, ["chromium", "firefox", "webkit"])
    first = client.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "ci-1"})
    assert first.status_code == 201, first.text
    second = client.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "ci-1"})
    assert second.json()["id"] == first.json()["id"]
    assert len(list(db.scalars(select(Job)))) == 3
    body["config"]["retries"] = 1
    assert (
        client.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "ci-1"}).status_code
        == 409
    )


def test_cross_workspace_read_and_cancel(client, account, db):
    _, project = account
    run = client.post("/api/v1/runs", json=payload(project)).json()
    client.post("/api/v1/auth/logout", json={})
    client.post(
        "/api/v1/auth/register",
        json={"email": "stranger@example.test", "password": "different-password-123"},
    )
    assert client.get(f"/api/v1/runs/{run['id']}").status_code == 404
    assert client.post(f"/api/v1/runs/{run['id']}/cancel", json={}).status_code == 404
    assert client.post("/api/v1/runs", json=payload(project)).status_code == 404


def test_viewer_cannot_start(client, account, db):
    workspace, project = account
    member = db.scalar(select(Member).where(Member.workspace_id == workspace["id"]))
    member.role = "viewer"
    db.commit()
    assert client.post("/api/v1/runs", json=payload(project)).status_code == 403


def test_scoped_api_keys(client, account, db):
    workspace, project = account
    created = client.post(
        f"/api/v1/workspaces/{workspace['id']}/api-keys",
        json={"name": "CI read only", "scopes": ["runs:read"]},
    )
    assert created.status_code == 201
    key = created.json()
    assert db.get(ApiKey, key["id"]).digest == digest(key["token"])
    headers = {"Authorization": "Bearer " + key["token"]}
    assert client.post("/api/v1/runs", headers=headers, json=payload(project)).status_code == 403
    assert (
        client.get(f"/api/v1/runs?workspace_id={workspace['id']}", headers=headers).status_code
        == 200
    )
    client.delete(f"/api/v1/workspaces/{workspace['id']}/api-keys/{key['id']}")
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_cancel_queued_matrix(client, account, db):
    _, project = account
    run = client.post("/api/v1/runs", json=payload(project, ["chromium", "firefox"])).json()
    response = client.post(f"/api/v1/runs/{run['id']}/cancel", json={})
    assert response.json()["status"] == "cancelled"
    assert {j.status for j in db.scalars(select(Job))} == {"cancelled"}
    assert db.get(Run, run["id"]).finished_at
    assert len(list(db.scalars(select(Event)))) == 4


def test_quota_matrix_counts_jobs(client, account, db):
    workspace, project = account
    from browsergrid.models import Workspace

    db.get(Workspace, workspace["id"]).daily_jobs = 2
    db.commit()
    assert (
        client.post(
            "/api/v1/runs", json=payload(project, ["chromium", "firefox", "webkit"])
        ).status_code
        == 429
    )
    assert not list(db.scalars(select(Job)))


def test_secrets_never_return_values(client, account, db):
    _, project = account
    value = "private-project-test-secret"
    assert (
        client.put(
            f"/api/v1/projects/{project['id']}/secrets", json={"name": "API_TOKEN", "value": value}
        ).status_code
        == 204
    )
    assert value not in client.get(f"/api/v1/projects/{project['id']}/secrets").text
    assert value not in db.get(Secret, (project["id"], "API_TOKEN")).ciphertext
    body = payload(project)
    body["config"]["env"] = {"PUBLIC_TEST_VALUE": value}
    run = client.post("/api/v1/runs", json=body).json()
    assert value not in client.get(f"/api/v1/runs/{run['id']}").text


def test_artifact_cross_workspace_and_scope(client, account, db, monkeypatch):
    from browsergrid.models import Artifact

    workspace, project = account
    rid = client.post("/api/v1/runs", json=payload(project)).json()["id"]
    job = db.scalar(select(Job).where(Job.run_id == rid))
    artifact = Artifact(
        run_id=rid,
        job_id=job.id,
        key="private/path",
        name="shot.png",
        kind="screenshot",
        size=20,
        mime="image/png",
    )
    db.add(artifact)
    db.commit()
    key = client.post(
        f"/api/v1/workspaces/{workspace['id']}/api-keys",
        json={"name": "no artifacts", "scopes": ["runs:read"]},
    ).json()
    assert (
        client.get(
            f"/api/v1/artifacts/{artifact.id}/download",
            headers={"Authorization": "Bearer " + key["token"]},
        ).status_code
        == 403
    )
    client.post("/api/v1/auth/logout", json={})
    client.post(
        "/api/v1/auth/register",
        json={"email": "outside@example.test", "password": "outside-password-123"},
    )
    assert client.get(f"/api/v1/artifacts/{artifact.id}/download").status_code == 404


def test_pending_artifacts_are_hidden_and_not_downloadable(client, account, db):
    from browsergrid.models import Artifact

    _, project = account
    rid = client.post("/api/v1/runs", json=payload(project)).json()["id"]
    job = db.scalar(select(Job).where(Job.run_id == rid))
    artifact = Artifact(
        run_id=rid,
        job_id=job.id,
        key="pending/object",
        name="shot.png",
        kind="screenshot",
        size=20,
        mime="image/png",
        ready=False,
    )
    db.add(artifact)
    db.commit()
    assert client.get(f"/api/v1/runs/{rid}/artifacts").json() == []
    assert client.get(f"/api/v1/artifacts/{artifact.id}/download").status_code == 409
