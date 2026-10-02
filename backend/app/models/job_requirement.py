"""
JobRequirement ORM model.

A single structured requirement extracted from a JobDescription.
Stores normalized skill names, importance, extraction type (explicit vs
inferred), and source span for full traceability (Req 2.3, 2.4, 2.5).
"""

from __future__ import annotations

import uuid
from typing import Any, TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import ExtractionType, ImportanceLevel, RequirementType
from backend.app.models.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.models.job_description import JobDescription


class JobRequirement(UUIDPrimaryKeyMixin, Base):
    """
    A structured requirement extracted from a job description.

    normalized_skills — JSONB array of canonical skill strings
    source_span       — {start: int, end: int} character offsets into raw_text
    """

    __tablename__ = "job_requirements"

    job_description_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        doc="FK → job_descriptions(id) ON DELETE CASCADE",
    )
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    requirement_type: Mapped[RequirementType] = mapped_column(
        String(20), nullable=False
    )
    importance: Mapped[ImportanceLevel] = mapped_column(
        String(10),
        nullable=False,
        default=ImportanceLevel.REQUIRED,
        server_default=ImportanceLevel.REQUIRED.value,
    )
    extraction_type: Mapped[ExtractionType] = mapped_column(
        String(10), nullable=False
    )
    normalized_skills: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        doc="Array of canonical skill name strings",
    )
    source_span: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, doc="{start: int, end: int}"
    )

    # Relationships
    job_description: Mapped["JobDescription"] = relationship(
        "JobDescription",
        back_populates="requirements",
    )

    def __repr__(self) -> str:
        return (
            f"<JobRequirement id={self.id} type={self.requirement_type} "
            f"importance={self.importance}>"
        )
