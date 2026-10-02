"""
SQLAlchemy engine and session factory.

All services obtain a database session via the ``get_db`` FastAPI dependency.
The engine is configured from the DATABASE_URL environment variable so that
no credentials are stored in source (Req 15, .env.example).
"""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", "postgresql://user:password@localhost:5432/recourse_db"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session and closes it
    when the request completes (success or error).

    Usage::

        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
