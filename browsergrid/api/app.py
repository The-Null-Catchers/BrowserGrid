import asyncio
import json
import secrets
import uuid
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from redis import Redis
from browsergrid import storage
from browsergrid.api.auth import authorize, browser_only, identity, issue_session, utc
from browsergrid.config import settings
from browsergrid.db import session, session_factory
from browsergrid.lifecycle import TERMINAL, transition
from browsergrid.models import (
    ApiKey,
    Artifact,
    Audit,
    Bundle,
    Event,
    Job,
    Member,
    Project,
    Run,
    Secret,
    Session,
    TestResult,
    User,
    Worker,
    Workspace,
    now,
)
from browsergrid.schemas import Credentials, KeyCreate, MemberCreate, Named, RunCreate, SecretCreate
from browsergrid.security import digest, encrypt, validate_bundle, validate_env
from browsergrid.run_service import enqueue_run, RunCreationError

app = FastAPI(title="BrowserGrid", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "Last-Event-ID"],
)
passwords = PasswordHasher()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(32))


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "X-Request-ID": str(uuid.uuid4()),
        }
    )
    return response


def redis():
    return Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2)


def limit(request, label, maximum, seconds=60):
    # Fail closed for abuse-sensitive writes if the limiter is unavailable.
    key = f"rate:{label}:{request.client.host if request.client else 'unknown'}"
    try:
        count = redis().eval(
            "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
            1,
            key,
            seconds,
        )
    except Exception:
        raise HTTPException(503, "Rate limiter unavailable")
    if count > maximum:
        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": str(seconds)})


def dump(row, fields):
    return {f: getattr(row, f) for f in fields.split()}


def project_access(db, p, project_id, write=False, scope="projects:read"):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    authorize(
        db,
        p,
        project.workspace_id,
        ("owner", "admin", "developer") if write else ("owner", "admin", "developer", "viewer"),
        scope,
    )
    return project


def run_access(db, p, run_id, write=False, scope="runs:read"):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    authorize(
        db,
        p,
        run.workspace_id,
        ("owner", "admin", "developer") if write else ("owner", "admin", "developer", "viewer"),
        scope,
    )
    return run


def audit(db, p, wid, action, resource):
    db.add(Audit(workspace_id=wid, actor_id=p.user_id, action=action, resource=resource))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(db: DBSession = Depends(session)):
    try:
        db.execute(text("SELECT 1"))
        redis().ping()
        storage.client().head_bucket(Bucket=settings().s3_bucket)
    except Exception:
        raise HTTPException(503, "Required service unavailable")
    return {"status": "ready"}


@app.post("/api/v1/auth/register", status_code=201)
def register(
    data: Credentials, request: Request, response: Response, db: DBSession = Depends(session)
):
    limit(request, "auth", 10)
    user = User(email=data.email, password_hash=passwords.hash(data.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Account already exists")
    issue_session(db, user, response)
    return {"id": user.id, "email": user.email}


@app.post("/api/v1/auth/login")
def login(
    data: Credentials, request: Request, response: Response, db: DBSession = Depends(session)
):
    limit(request, "auth", 10)
    user = db.scalar(select(User).where(User.email == data.email))
    try:
        passwords.verify(user.password_hash if user else DUMMY_HASH, data.password)
    except VerificationError:
        raise HTTPException(401, "Invalid credentials")
    if not user:
        raise HTTPException(401, "Invalid credentials")
    old = request.cookies.get("bg_session")
    if old:
        previous = db.get(Session, digest(old))
        if previous:
            db.delete(previous)
    issue_session(db, user, response)
    return {"id": user.id, "email": user.email}


@app.post("/api/v1/auth/logout", status_code=204)
def logout(
    request: Request, response: Response, p=Depends(identity), db: DBSession = Depends(session)
):
    browser_only(p)
    record = db.get(Session, digest(request.cookies.get("bg_session", "")))
    if record:
        db.delete(record)
        db.commit()
    response.delete_cookie("bg_session", path="/")


@app.get("/api/v1/me")
def me(p=Depends(identity), db: DBSession = Depends(session)):
    return dump(db.get(User, p.user_id), "id email")


@app.post("/api/v1/workspaces", status_code=201)
def create_workspace(
    data: Named, request: Request, p=Depends(identity), db: DBSession = Depends(session)
):
    browser_only(p)
    limit(request, "workspace", 10)
    workspace = Workspace(name=data.name)
    db.add(workspace)
    db.flush()
    db.add(Member(workspace_id=workspace.id, user_id=p.user_id, role="owner"))
    db.commit()
    return dump(workspace, "id name concurrency")


@app.get("/api/v1/workspaces")
def workspaces(
    p=Depends(identity), db: DBSession = Depends(session), offset: int = 0, limit: int = 50
):
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, "Invalid pagination")
    q = select(Workspace).join(Member).where(Member.user_id == p.user_id)
    if p.key:
        q = q.where(Workspace.id == p.key.workspace_id)
    return [
        dump(w, "id name concurrency")
        for w in db.scalars(q.order_by(Workspace.created_at).offset(offset).limit(limit))
    ]


@app.post("/api/v1/workspaces/{wid}/members", status_code=201)
def add_member(wid: str, data: MemberCreate, p=Depends(identity), db: DBSession = Depends(session)):
    authorize(db, p, wid, ("owner", "admin"))
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user:
        raise HTTPException(404, "User must register first")
    if db.get(Member, (wid, user.id)):
        raise HTTPException(409, "Already a member")
    db.add(Member(workspace_id=wid, user_id=user.id, role=data.role))
    audit(db, p, wid, "member.added", user.id)
    db.commit()
    return {"user_id": user.id, "role": data.role}


@app.post("/api/v1/workspaces/{wid}/projects", status_code=201)
def create_project(wid: str, data: Named, p=Depends(identity), db: DBSession = Depends(session)):
    authorize(db, p, wid, ("owner", "admin", "developer"))
    project = Project(workspace_id=wid, name=data.name)
    db.add(project)
    db.commit()
    return dump(project, "id workspace_id name settings")


@app.get("/api/v1/workspaces/{wid}/projects")
def projects(
    wid: str,
    p=Depends(identity),
    db: DBSession = Depends(session),
    offset: int = 0,
    limit: int = 50,
):
    authorize(db, p, wid, scope="projects:read")
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, "Invalid pagination")
    return [
        dump(v, "id workspace_id name settings")
        for v in db.scalars(
            select(Project)
            .where(Project.workspace_id == wid)
            .order_by(Project.created_at)
            .offset(offset)
            .limit(limit)
        )
    ]


@app.put("/api/v1/projects/{pid}/secrets", status_code=204)
def secret(pid: str, data: SecretCreate, p=Depends(identity), db: DBSession = Depends(session)):
    project = project_access(db, p, pid, True, scope=None)
    try:
        validate_env({data.name: data.value})
    except ValueError as e:
        raise HTTPException(422, str(e))
    record = db.get(Secret, (pid, data.name))
    if record:
        record.ciphertext = encrypt(data.value)
    else:
        db.add(Secret(project_id=pid, name=data.name, ciphertext=encrypt(data.value)))
    audit(db, p, project.workspace_id, "secret.changed", pid)
    db.commit()


@app.get("/api/v1/projects/{pid}/secrets")
def secret_names(pid: str, p=Depends(identity), db: DBSession = Depends(session)):
    project_access(db, p, pid, True, scope=None)
    return [{"name": v} for v in db.scalars(select(Secret.name).where(Secret.project_id == pid))]


@app.post("/api/v1/workspaces/{wid}/api-keys", status_code=201)
def key_create(
    wid: str,
    data: KeyCreate,
    request: Request,
    p=Depends(identity),
    db: DBSession = Depends(session),
):
    authorize(db, p, wid, ("owner", "admin"))
    limit(request, "keys", 10)
    token = "bg_live_" + secrets.token_urlsafe(40)
    key = ApiKey(
        workspace_id=wid,
        creator_id=p.user_id,
        name=data.name,
        digest=digest(token),
        scopes=data.scopes,
        expires_at=now() + timedelta(days=data.expires_days),
    )
    db.add(key)
    db.flush()
    audit(db, p, wid, "api_key.created", key.id)
    db.commit()
    return {"id": key.id, "token": token, "scopes": key.scopes, "expires_at": key.expires_at}


@app.delete("/api/v1/workspaces/{wid}/api-keys/{kid}", status_code=204)
def key_revoke(wid: str, kid: str, p=Depends(identity), db: DBSession = Depends(session)):
    authorize(db, p, wid, ("owner", "admin"))
    key = db.get(ApiKey, kid)
    if not key or key.workspace_id != wid:
        raise HTTPException(404, "Key not found")
    key.revoked = True
    audit(db, p, wid, "api_key.revoked", kid)
    db.commit()


@app.post("/api/v1/projects/{pid}/bundles", status_code=201)
async def upload_bundle(
    pid: str,
    file: UploadFile,
    request: Request,
    p=Depends(identity),
    db: DBSession = Depends(session),
):
    project_access(db, p, pid, True, scope="runs:write")
    limit(request, "upload", 10)
    data = await file.read(settings().max_bundle_bytes + 1)
    try:
        validate_bundle(data)
    except (ValueError, Exception) as exc:
        raise HTTPException(422, "Invalid or unsafe ZIP bundle") from exc
    bundle = Bundle(id=str(uuid.uuid4()), project_id=pid, size=len(data), key="")
    bundle.key = f"bundles/{pid}/{bundle.id}.zip"
    await asyncio.to_thread(storage.put, bundle.key, data, "application/zip")
    db.add(bundle)
    db.commit()
    return {"id": bundle.id, "size": bundle.size}


@app.post("/api/v1/runs", status_code=201)
def create_run(
    data: RunCreate,
    request: Request,
    p=Depends(identity),
    db: DBSession = Depends(session),
    idempotency_key: str | None = Header(default=None),
):
    project = project_access(db, p, data.project_id, True, "runs:write")
    limit(request, "run", 30)
    try:
        result = enqueue_run(db, project, p, data, idempotency_key)
    except RunCreationError as exc:
        db.rollback()
        raise HTTPException(exc.status, exc.detail) from exc
    try:
        redis().lpush("bg:wakeup", "1")
    except Exception:
        pass  # Durable DB queue survives notification failure.
    return result


@app.get("/api/v1/runs")
def runs(
    workspace_id: str,
    project_id: str | None = None,
    status: str | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 30,
    p=Depends(identity),
    db: DBSession = Depends(session),
):
    authorize(db, p, workspace_id, scope="runs:read")
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, "Invalid pagination")
    query = select(Run).where(Run.workspace_id == workspace_id)
    if project_id:
        query = query.where(Run.project_id == project_id)
    if status:
        query = query.where(Run.status == status)
    if q:
        query = query.where(Run.id.contains(q[:100]))
    return [
        dump(v, "id project_id status trigger created_at finished_at")
        for v in db.scalars(query.order_by(Run.created_at.desc()).offset(offset).limit(limit))
    ]


@app.get("/api/v1/runs/{rid}")
def run_detail(rid: str, p=Depends(identity), db: DBSession = Depends(session)):
    run = run_access(db, p, rid)
    # Secret env values are never returned, including public run envs.
    config = {k: v for k, v in run.config.items() if k not in {"env", "source"}}
    config["source"] = {k: v for k, v in run.config["source"].items() if k != "code"}
    return {
        **dump(run, "id project_id status trigger created_at finished_at cancel_requested"),
        "config": config,
        "jobs": [
            dump(
                j, "id browser viewport status worker_id started_at finished_at error_code runtime"
            )
            for j in db.scalars(select(Job).where(Job.run_id == rid))
        ],
    }


@app.post("/api/v1/runs/{rid}/cancel")
def cancel(rid: str, p=Depends(identity), db: DBSession = Depends(session)):
    run = run_access(db, p, rid, True, "runs:write")
    # Serialize cancellation with worker result persistence / lease transitions.
    db.scalar(select(Workspace).where(Workspace.id == run.workspace_id).with_for_update())
    db.refresh(run)
    if run.status in TERMINAL:
        return {"status": run.status}
    run.cancel_requested = True
    for job in db.scalars(
        select(Job).where(Job.run_id == rid, Job.status == "queued").with_for_update()
    ):
        transition(db, job, "cancelled")
    db.commit()
    return {"status": run.status, "cancel_requested": True}


@app.get("/api/v1/runs/{rid}/tests")
def tests(
    rid: str,
    offset: int = 0,
    limit: int = 100,
    p=Depends(identity),
    db: DBSession = Depends(session),
):
    run_access(db, p, rid)
    if offset < 0 or not 1 <= limit <= 200:
        raise HTTPException(422, "Invalid pagination")
    return [
        dump(t, "id job_id file title suite status duration_ms retry error")
        for t in db.scalars(
            select(TestResult)
            .join(Job)
            .where(Job.run_id == rid)
            .order_by(TestResult.id)
            .offset(offset)
            .limit(limit)
        )
    ]


@app.get("/api/v1/runs/{rid}/artifacts")
def artifacts(
    rid: str,
    p=Depends(identity),
    db: DBSession = Depends(session),
    offset: int = 0,
    limit: int = 50,
):
    run_access(db, p, rid, scope="artifacts:read")
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, "Invalid pagination")
    return [
        dump(a, "id job_id name kind size mime created_at")
        for a in db.scalars(
            select(Artifact)
            .where(Artifact.run_id == rid, Artifact.ready.is_(True))
            .order_by(Artifact.created_at)
            .offset(offset)
            .limit(limit)
        )
    ]


@app.get("/api/v1/artifacts/{aid}/download")
def artifact_download(aid: str, p=Depends(identity), db: DBSession = Depends(session)):
    artifact = db.get(Artifact, aid)
    if not artifact:
        raise HTTPException(404, "Artifact not found")
    run_access(db, p, artifact.run_id, scope="artifacts:read")
    if artifact.expires_at and utc(artifact.expires_at) <= now():
        raise HTTPException(410, "Artifact expired")
    if not artifact.ready:
        raise HTTPException(409, "Artifact upload is not complete")
    return {"url": storage.signed(artifact.key, artifact.name), "expires_in": 120}


@app.get("/api/v1/runs/{rid}/events")
async def events(
    rid: str,
    request: Request,
    after: int = 0,
    last_event_id: str | None = Header(default=None),
    p=Depends(identity),
    db: DBSession = Depends(session),
):
    run_access(db, p, rid)
    try:
        cursor = max(after, int(last_event_id or 0))
    except ValueError:
        raise HTTPException(422, "Invalid cursor")

    async def stream():
        nonlocal cursor
        # One bounded query at a time; never retain a DB transaction while waiting.
        for _ in range(2400):
            if await request.is_disconnected():
                return

            def fetch():
                with session_factory()() as s:
                    run_access(s, p, rid)
                    records = s.scalars(
                        select(Event)
                        .where(Event.run_id == rid, Event.id > cursor)
                        .order_by(Event.id)
                        .limit(200)
                    ).all()
                    return [
                        (
                            e.id,
                            e.kind,
                            {
                                "id": e.id,
                                "job_id": e.job_id,
                                "kind": e.kind,
                                "data": e.data,
                                "created_at": e.created_at.isoformat(),
                            },
                        )
                        for e in records
                    ], s.get(Run, rid).status

            try:
                batch, state = await asyncio.to_thread(fetch)
            except HTTPException:
                return
            for eid, kind, data in batch:
                cursor = eid
                yield f"id: {eid}\nevent: {kind}\ndata: {json.dumps(data)}\n\n"
            if state in TERMINAL and not batch:
                yield "event: complete\ndata: {}\n\n"
                return
            if not batch:
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )


@app.get("/api/v1/workspaces/{wid}/workers")
def workers(wid: str, p=Depends(identity), db: DBSession = Depends(session)):
    authorize(db, p, wid, ("owner", "admin"), scope=None)
    # Do not leak other tenants' job IDs.
    active = set(db.scalars(select(Job.id).where(Job.workspace_id == wid)))
    return [
        {
            "id": w.id,
            "healthy": (now() - utc(w.heartbeat_at)).total_seconds() < settings().lease_seconds,
            "busy": bool(w.job_id),
            "job_id": w.job_id if w.job_id in active else None,
            "version": w.version,
        }
        for w in db.scalars(select(Worker).limit(100))
    ]
