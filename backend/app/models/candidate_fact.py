"""
CandidateFact ORM model.

Represents a single discrete claim extracted from a candidate's resume
(a skill, project, responsibility, etc.). Each fact carries its source
span so verification can trace it back to the original document.

Key invariants (enforced by the service layer, not the DB alone):
- original_claim_text is set once at creation and never mutated (Req 3.9, Property 7)
- verification_status starts as NeedsConfirmation for auto-extracted facts (Req 3.3)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import ClaimType, VerificationStatus
from backend.app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, UpdatedAtMixin

if TYPE_CHECKING:
    from backend.app.models.resume_document import ResumeDocument


class CandidateFact(UUIDPrimaryKeyMixin, TimestampMixin, UpdatedAtMixin, Base):
    """
    A discrete, sourced claim extracted from a candidate's resume.

    claim_text          — current (editable) text; may be updated by candidate
    original_claim_text — set once at creation; never mutated (audit trail)
    source_span         — {start: int, end: int} character offsets
    metadata_           — JSON bag for related skill/project/experience links
    """

    __tablename__ = "candidate_facts"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    claim_text: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Current claim text (max 2000 chars enforced by service)"
    )
    original_claim_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Immutable original text set at creation time",
    )
    claim_type: Mapped[ClaimType] = mapped_column(
        String(20), nullable=False
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        doc="FK → resume_documents(id) ON DELETE CASCADE",
    )
    source_span: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, doc="{start: int, end: int}"
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        String(30),
        nullable=False,
        default=VerificationStatus.NEEDS_CONFIRMATION,
        server_default=VerificationStatus.NEEDS_CONFIRMATION.value,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Related skills, projects, experience associations",
    )

    # Relationships
    source_document: Mapped["ResumeDocument"] = relationship(
        "ResumeDocument",
        back_populates="candidate_facts",
    )

    def __repr__(self) -> str:
        return (
            f"<CandidateFact id={self.id} type={self.claim_type} "
            f"status={self.verification_status}>"
        )
