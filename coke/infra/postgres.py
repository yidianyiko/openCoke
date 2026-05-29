from __future__ import annotations

from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from coke.config import Settings


def create_engine(settings: Settings) -> Engine:
    return sqlalchemy_create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
