"""
Pydantic schemas for the recourse engine and optimizer.

Covers:
- RecourseGenerateRequest / ProposedEditResponse / RecourseResult — generate endpoint
- OptimizationConfig — optimizer configuration
- InfeasibleResult  — returned when no valid edit set can satisfy constraints

Requirements: 5.1–5.8, 6.1–6.7
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ── Optimizer configuration ───────────────────────────────────────────────────


class OptimizationConfig(BaseModel):
    """
    Four-weight edit cost configuration.

    All four weights must sum to 1.0 (±1e-9 tolerance).
    """

    levenshtein_weight: float = Field(0.25, ge=0.0, le=1.0)
    changed_statements_weight: float = Field(0.25, ge=0.0, le=1.0)
    semantic_change_weight: float = Field(0.25, ge=0.0, le=1.0)
    moved_sections_weight: float = Field(0.25, ge=0.0, le=1.0)
    threshold: float = Field(0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def weights_must_sum_to_one(self) -> "OptimizationConfig":
        total = (
            self.levenshtein_weight
            + self.changed_statements_weight
            + self.semantic_change_weight
            + self.moved_sections_weight
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"Optimization weights must sum to 1.0; got {total:.6f}."
            )
        return self


# ── Request / Response schemas ────────────────────────────────────────────────


class RecourseGenerateRequest(BaseModel):
    """Request body for POST /api/recourse/generate."""

    resume_version_id: uuid.UUID
    job_description_id: uuid.UUID
    optimization_config: OptimizationConfig = Field(
        default_factory=OptimizationConfig
    )


class ProposedEditResponse(BaseModel):
    """JSON shape for a single ProposedEdit in the API response."""

    id: uuid.UUID
    original_text: str
    proposed_text: str
    edit_type: str
    evidence_fact_ids: list[uuid.UUID]
    job_requirement_ids: list[uuid.UUID]
    verification_status: str
    edit_cost: float
    score_contribution: float

    model_config = {"from_attributes": True}


class PartialResult(BaseModel):
    """Lowest-cost partial edit set returned when optimization is infeasible."""

    edits: list[ProposedEditResponse]
    total_edit_cost: float
    projected_score: float


class RecourseGenerateResponse(BaseModel):
    """
    Full response for POST /api/recourse/generate.

    status == "feasible"   → accepted_edits, total_edit_cost, projected_score,
                             projected_decision all populated
    status == "infeasible" → reason, detail, constraints_violated, partial_result
    """

    recourse_id: uuid.UUID
    status: Literal["feasible", "infeasible"]

    # Feasible fields
    accepted_edits: list[ProposedEditResponse] | None = None
    total_edit_cost: float | None = None
    projected_score: float | None = None
    projected_decision: Literal["pass", "fail"] | None = None

    # Infeasible fields
    reason: str | None = None
    detail: str | None = None
    constraints_violated: list[str] | None = None
    partial_result: PartialResult | None = None


# ── Internal data-transfer objects ───────────────────────────────────────────


class EditCandidate(BaseModel):
    """Intermediate DTO used inside the recourse engine before DB persistence."""

    original_text: str
    proposed_text: str
    edit_type: str
    evidence_fact_ids: list[uuid.UUID]
    job_requirement_ids: list[uuid.UUID]
    score_contribution: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
