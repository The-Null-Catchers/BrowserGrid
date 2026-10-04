import os

os.environ["BG_DATABASE_URL"] = "sqlite://"
from cryptography.fernet import Fernet

os.environ["BG_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from browsergrid.db import Base, session
from browsergrid.api.app import app
import browsergrid.api.app as api_module


class FakeLimiter:
    def eval(self, *args):
        return 1

    def lpush(self, *args):
        return 1


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as s:
        yield s
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db, monkeypatch):
    def get_db():
        yield db

    app.dependency_overrides[session] = get_db
    monkeypatch.setattr(api_module, "redis", lambda: FakeLimiter())
    with TestClient(app, headers={"Origin": "http://localhost:3000"}) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def account(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.test", "password": "secure-test-password-123"},
    )
    assert response.status_code == 201, response.text
    workspace = client.post("/api/v1/workspaces", json={"name": "QA"}).json()
    project = client.post(
        f"/api/v1/workspaces/{workspace['id']}/projects", json={"name": "Fixture"}
    ).json()
    return workspace, project
