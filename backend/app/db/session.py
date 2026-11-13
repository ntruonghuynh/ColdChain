"""Database engine and session management."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.sqlalchemy_url(),
        pool_size=settings.db_pool_size,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": settings.db_connect_timeout_s,
            # Every session works in UTC so database-side now() and casts are unambiguous.
            "options": "-c timezone=UTC",
        },
    )


@lru_cache
def get_engine() -> Engine:
    return build_engine(get_settings())


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
