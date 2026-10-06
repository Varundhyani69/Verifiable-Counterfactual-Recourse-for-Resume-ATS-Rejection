"""
SQLAlchemy engine and session factory.

All services obtain a database session via the ``get_db`` FastAPI dependency.
The engine is configured from the DATABASE_URL environment variable so that
no credentials are stored in source (Req 15, .env.example).

Engine creation is deferred until first use so that importing models in unit
tests (which mock the DB) does not require a live database connection.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Always use the psycopg2 driver explicitly so that SQLAlchemy does not
# attempt to load the psycopg v3 async driver when the scheme is bare
# "postgresql://".  The psycopg2-binary package is installed in the dev
# environment; psycopg (v3) is not.
_RAW_URL: str = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg2://user:password@localhost:5432/recourse_db"
)

# Normalise bare "postgresql://" → "postgresql+psycopg2://" so that
# existing .env files without the explicit driver suffix still work.
DATABASE_URL: str = (
    _RAW_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    if _RAW_URL.startswith("postgresql://")
    else _RAW_URL
)

# ── Lazy engine ───────────────────────────────────────────────────────────────
# The engine and session factory are created on first access so that importing
# this module in unit tests (which never touch the DB) does not fail.

_engine: Any = None
_SessionLocal: Any = None


def _get_engine() -> Any:
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    return _engine


def _get_session_factory() -> Any:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=_get_engine()
        )
    return _SessionLocal


# Public aliases used throughout the codebase.
class _LazyEngine:
    """Proxy that creates the real engine on first attribute access."""

    def __getattr__(self, name: str) -> Any:
        return getattr(_get_engine(), name)

    def __repr__(self) -> str:  # pragma: no cover
        return repr(_get_engine())


class _LazySessionLocal:
    """Proxy that creates the session factory on first call."""

    def __call__(self, **kw: Any) -> Any:
        return _get_session_factory()(**kw)

    def __getattr__(self, name: str) -> Any:
        return getattr(_get_session_factory(), name)


engine = _LazyEngine()  # type: ignore[assignment]
SessionLocal = _LazySessionLocal()  # type: ignore[assignment]


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session and closes it
    when the request completes (success or error).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
