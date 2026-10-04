import secrets
from dataclasses import dataclass
from datetime import timedelta, timezone
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from browsergrid.db import session
from browsergrid.models import ApiKey, Member, Session, User, now
from browsergrid.security import digest
from browsergrid.config import settings


@dataclass
class Principal:
    user_id: str
    key: ApiKey | None = None
    session_digest: str | None = None


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def identity(request: Request, db: DBSession = Depends(session)):
    bearer = request.headers.get("authorization", "")
    if bearer.startswith("Bearer "):
        key = db.scalar(select(ApiKey).where(ApiKey.digest == digest(bearer[7:])))
        if not key or key.revoked or utc(key.expires_at) <= now():
            raise HTTPException(401, "Invalid API key")
        key.last_used_at = now()
        db.commit()
        return Principal(key.creator_id, key)
    token = request.cookies.get("bg_session", "")
    record = db.get(Session, digest(token)) if token else None
    if not record or utc(record.expires_at) <= now():
        raise HTTPException(401, "Authentication required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") not in settings().origins.split(","):
            raise HTTPException(403, "Allowed Origin header required for cookie mutations")
    return Principal(record.user_id, session_digest=record.digest)


def authorize(
    db, principal, workspace_id, roles=("owner", "admin", "developer", "viewer"), scope=None
):
    if principal.session_digest:
        active_session = db.get(Session, principal.session_digest)
        if not active_session or utc(active_session.expires_at) <= now():
            raise HTTPException(401, "Session expired or revoked")
    if principal.key:
        active_key = db.get(ApiKey, principal.key.id)
        if not active_key or active_key.revoked or utc(active_key.expires_at) <= now():
            raise HTTPException(401, "API key expired or revoked")
    member = db.get(Member, (workspace_id, principal.user_id))
    if not member:
        raise HTTPException(404, "Workspace not found")
    if member.role not in roles:
        raise HTTPException(403, "Insufficient workspace permission")
    if principal.key:
        if principal.key.workspace_id != workspace_id:
            raise HTTPException(404, "Workspace not found")
        if not scope or scope not in principal.key.scopes:
            raise HTTPException(403, "API key scope denied")
    return member


def browser_only(principal):
    if principal.key:
        raise HTTPException(403, "This operation requires a browser session")


def issue_session(db, user: User, response):
    token = secrets.token_urlsafe(48)
    db.add(Session(digest=digest(token), user_id=user.id, expires_at=now() + timedelta(days=30)))
    db.commit()
    response.set_cookie(
        "bg_session",
        token,
        httponly=True,
        secure=settings().secure_cookies,
        samesite="lax",
        max_age=30 * 86400,
        path="/",
    )
