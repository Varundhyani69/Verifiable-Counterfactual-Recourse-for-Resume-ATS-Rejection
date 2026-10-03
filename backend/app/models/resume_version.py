"""
ResumeVersion ORM model.

A snapshot of a resume at a specific point in the recourse workflow,
with its associated ATS score and pass/fail decision.

version_number=1 is always the baseline (unmodified) scoring result.
Each accepted recourse produces version_number = prior_max + 1.
UNIQUE(original_resume_id, version_number) is enforced at the DB level.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import ATSDecision
from backend.app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.models.proposed_edit import ProposedEdit
    from backend.app.models.resume_document import ResumeDocument


class ResumeVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Immutable snapshot of a resume at a particular workflow stage.

    ats_score and decision are NULL until the ATS scorer runs against
    this version.
    """

    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint(
            "original_resume_id",
            "version_number",
            name="uq_resume_versions_resume_version",
        ),
    )

    original_resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="FK → resume_documents(id)",
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="1 = baseline; increments by 1 for each accepted recourse",
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Full text of this resume version"
    )
    ats_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[ATSDecision | None] = mapped_column(
        String(4), nullable=True, doc="'pass' or 'fail'"
    )

    # Relationships
    original_resume: Mapped[ResumeDocument] = relationship(
        "ResumeDocument",
        back_populates="resume_versions",
    )
    proposed_edits: Mapped[list[ProposedEdit]] = relationship(
        "ProposedEdit",
        back_populates="resume_version",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ResumeVersion id={self.id} v={self.version_number} "
            f"score={self.ats_score} decision={self.decision}>"
        )
