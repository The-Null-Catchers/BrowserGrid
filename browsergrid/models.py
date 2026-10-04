from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from browsergrid.db import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Session(Base):
    __tablename__ = "sessions"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    concurrency: Mapped[int] = mapped_column(Integer, default=2)
    daily_jobs: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Member(Base):
    __tablename__ = "workspace_members"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Secret(Base):
    __tablename__ = "secrets"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    scopes: Mapped[list] = mapped_column(JSON)
    creator_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Run(Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "idempotency_key"),
        Index("ix_runs_project_created", "project_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    config: Mapped[dict] = mapped_column(JSON)
    request_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(Base):
    __tablename__ = "run_jobs"
    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    browser: Mapped[str] = mapped_column(String(20))
    viewport: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    worker_id: Mapped[str | None] = mapped_column(String(100))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(50))
    runtime: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Event(Base):
    __tablename__ = "run_events"
    __table_args__ = (Index("ix_events_run_id", "run_id", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id"))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("run_jobs.id"))
    kind: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TestResult(Base):
    __tablename__ = "test_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("run_jobs.id"), index=True)
    file: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(1000))
    suite: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(30))
    duration_ms: Mapped[int] = mapped_column(Integer)
    retry: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("run_jobs.id"))
    key: Mapped[str] = mapped_column(String(1000), unique=True)
    name: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(30))
    size: Mapped[int] = mapped_column(Integer)
    mime: Mapped[str] = mapped_column(String(100))
    ready: Mapped[bool] = mapped_column(Boolean, default=False, server_default="true")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Bundle(Base):
    __tablename__ = "bundles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    key: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(Integer)
    ready: Mapped[bool] = mapped_column(Boolean, default=False, server_default="true")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Worker(Base):
    __tablename__ = "workers"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    job_id: Mapped[str | None] = mapped_column(String(36))
    completed: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[str] = mapped_column(String(40))


class Audit(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    resource: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
