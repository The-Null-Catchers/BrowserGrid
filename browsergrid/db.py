from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from browsergrid.config import settings


class Base(DeclarativeBase):
    pass


@lru_cache
def engine():
    return create_engine(settings().database_url, pool_pre_ping=True)


@lru_cache
def session_factory():
    return sessionmaker(engine(), expire_on_commit=False)


def session():
    with session_factory()() as db:
        yield db
