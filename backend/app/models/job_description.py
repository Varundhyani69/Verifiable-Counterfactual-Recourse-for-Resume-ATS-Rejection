"""
JobDescription ORM model.

Stores the raw text of a submitted job description. Extracted structured
requirements live in the JobRequirement table (one-to-many).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.models.job_requirement import JobRequirement


class JobDescription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Raw job description text with its extracted requirements."""

    __tablename__ = "job_descriptions"

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    requirements: Mapped[list[JobRequirement]] = relationship(
        "JobRequirement",
        back_populates="job_description",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        preview = self.raw_text[:60].replace("\n", " ") if self.raw_text else ""
        return f"<JobDescription id={self.id} preview='{preview}...'>"
