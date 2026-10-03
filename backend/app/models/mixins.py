"""
SQLAlchemy ORM mixins shared across domain models.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.exceptions import ImmutableRecordError


class UUIDPrimaryKeyMixin:
    """Adds a server-generated UUID primary key to any model."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )


class TimestampMixin:
    """Adds created_at timestamp (server-side, immutable after creation)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)


class UpdatedAtMixin:
    """Adds updated_at timestamp that must be stamped on every PATCH."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AppendOnlyMixin:
    """
    Prevents any post-creation mutation of a model instance.

    Applied to ExperimentRun to enforce the append-only invariant
    required by Requirement 10.8 and Property 24.

    Any attempt to set an attribute after the instance has been
    persisted (i.e., after ``id`` is assigned) raises ImmutableRecordError.
    """

    _is_persisted: bool = False

    def __setattr__(self, key: str, value: object) -> None:
        # Allow setting during __init__ and before first persist
        if key.startswith("_") or not self._is_persisted:
            object.__setattr__(self, key, value)
            return
        raise ImmutableRecordError(type(self).__name__)

    def mark_persisted(self) -> None:
        """Call this after the first DB flush to activate immutability."""
        object.__setattr__(self, "_is_persisted", True)
