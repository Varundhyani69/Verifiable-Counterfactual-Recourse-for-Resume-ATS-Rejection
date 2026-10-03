"""
ExperimentRun ORM model and its junction table.

ExperimentRun is append-only (Req 10.8, Property 24).
AppendOnlyMixin raises ImmutableRecordError on any post-creation mutation.

The experiment_run_edits junction table records ALL ProposedEdits generated
during a session — including rejected ones — not just the accepted set (Req 10.4).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import BaselineMethod
from backend.app.models.mixins import AppendOnlyMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.models.proposed_edit import ProposedEdit


# ── Junction: ExperimentRun ↔ ProposedEdit (all edits, not just accepted) ─────
experiment_run_edits = Table(
    "experiment_run_edits",
    Base.metadata,
    Column(
        "experiment_run_id",
        UUID(as_uuid=True),
        ForeignKey("experiment_runs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "proposed_edit_id",
        UUID(as_uuid=True),
        ForeignKey("proposed_edits.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class ExperimentRun(AppendOnlyMixin, UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Append-only log of a single recourse evaluation session.

    model_configuration — JSONB capturing all model names, weights, and
                          hyperparameters needed to reproduce the run (Req 10.2)
    grounding_metrics   — JSONB with three rate values in [0.0, 1.0] (Req 10.5)
    random_seed         — integer seed for any stochastic component; NULL if none (Req 10.3)

    Once created, no field may be modified (AppendOnlyMixin enforces this).
    """

    __tablename__ = "experiment_runs"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resume_documents.id"),
        nullable=False,
        doc="FK → resume_documents(id) (Req 14.5)",
    )
    job_description_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.id"),
        nullable=False,
        doc="FK → job_descriptions(id) (Req 14.5)",
    )
    model_configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        doc=(
            "Keys: sbert_model, sbert_version, spacy_model, spacy_version, "
            "ats_skill_weight, ats_sbert_weight, threshold, edit_cost_weights"
        ),
    )
    baseline_method: Mapped[BaselineMethod] = mapped_column(
        String(20),
        nullable=False,
        doc="One of: original_resume, generic_llm, proposed",
    )
    original_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Partial result score for infeasible runs",
    )
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    decision_flipped: Mapped[bool] = mapped_column(Boolean, nullable=False)
    total_edit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    grounding_metrics: Mapped[dict[str, float]] = mapped_column(
        JSONB,
        nullable=False,
        doc=(
            "Keys: evidence_grounding_rate, unsupported_claim_rate, "
            "original_fact_preservation_rate — all in [0.0, 1.0]"
        ),
    )
    random_seed: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="NULL if no stochastic component was used",
    )

    # Relationships
    all_edits: Mapped[list[ProposedEdit]] = relationship(
        "ProposedEdit",
        secondary=experiment_run_edits,
        doc="ALL generated edits including rejected ones (Req 10.4)",
    )

    def __repr__(self) -> str:
        return (
            f"<ExperimentRun id={self.id} method={self.baseline_method} "
            f"flipped={self.decision_flipped} score={self.original_score:.3f}"
            f"→{self.final_score:.3f}>"
        )
