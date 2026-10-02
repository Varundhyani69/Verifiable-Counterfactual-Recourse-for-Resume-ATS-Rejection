"""
ProposedEdit ORM model and its two junction tables.

A ProposedEdit is a single atomic recourse operation (rephrase, surface,
reorder, normalize, reorganize, remove_redundancy) with full provenance.

Junction tables:
  proposed_edit_facts        — links edits to their grounding CandidateFacts
  proposed_edit_requirements — links edits to the JobRequirements they address
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String, Table, Text, Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import EditType, VerificationStatus
from backend.app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.models.candidate_fact import CandidateFact
    from backend.app.models.job_requirement import JobRequirement
    from backend.app.models.resume_version import ResumeVersion


# ── Junction: ProposedEdit ↔ CandidateFact ────────────────────────────────────
proposed_edit_facts = Table(
    "proposed_edit_facts",
    Base.metadata,
    Column(
        "proposed_edit_id",
        UUID(as_uuid=True),
        ForeignKey("proposed_edits.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "candidate_fact_id",
        UUID(as_uuid=True),
        ForeignKey("candidate_facts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

# ── Junction: ProposedEdit ↔ JobRequirement ───────────────────────────────────
proposed_edit_requirements = Table(
    "proposed_edit_requirements",
    Base.metadata,
    Column(
        "proposed_edit_id",
        UUID(as_uuid=True),
        ForeignKey("proposed_edits.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "job_requirement_id",
        UUID(as_uuid=True),
        ForeignKey("job_requirements.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class ProposedEdit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A single atomic recourse operation with full provenance.

    edit_cost        — composite [0.0, 1.0] cost (filled by Optimizer)
    score_contribution — estimated ATS score delta from applying this edit
    verification_status — starts as NeedsConfirmation; updated by Verifier
    """

    __tablename__ = "proposed_edits"

    resume_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="FK → resume_versions(id) (Req 14.3)",
    )
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_text: Mapped[str] = mapped_column(Text, nullable=False)
    edit_type: Mapped[EditType] = mapped_column(String(30), nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        String(30),
        nullable=False,
        default=VerificationStatus.NEEDS_CONFIRMATION,
        server_default=VerificationStatus.NEEDS_CONFIRMATION.value,
    )
    edit_cost: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, doc="[0.0, 1.0] composite cost"
    )
    score_contribution: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, doc="Estimated ATS score delta"
    )

    # Relationships
    resume_version: Mapped["ResumeVersion"] = relationship(
        "ResumeVersion", back_populates="proposed_edits"
    )
    evidence_facts: Mapped[list["CandidateFact"]] = relationship(
        "CandidateFact", secondary=proposed_edit_facts
    )
    job_requirements: Mapped[list["JobRequirement"]] = relationship(
        "JobRequirement", secondary=proposed_edit_requirements
    )

    def __repr__(self) -> str:
        return (
            f"<ProposedEdit id={self.id} type={self.edit_type} "
            f"status={self.verification_status} cost={self.edit_cost:.3f}>"
        )
