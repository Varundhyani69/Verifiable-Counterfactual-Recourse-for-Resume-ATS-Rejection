"""
Pydantic schemas for the experiment logger.

Covers ExperimentRunCreate (input validation), ExperimentRunSummary (list view),
ExperimentRunResponse (full detail), ExperimentReport (with edits), and the
PaginatedResult wrapper used by ``GET /api/experiments``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class GroundingMetrics(BaseModel):
    """Three rate values each in [0.0, 1.0]."""

    evidence_grounding_rate: float = Field(..., ge=0.0, le=1.0)
    unsupported_claim_rate: float = Field(..., ge=0.0, le=1.0)
    original_fact_preservation_rate: float = Field(..., ge=0.0, le=1.0)


class ExperimentRunCreate(BaseModel):
    """
    Payload for ``POST /api/experiments``.

    All 13 required fields must be present and valid.
    """

    model_config = {"protected_namespaces": ()}

    resume_id: uuid.UUID
    job_description_id: uuid.UUID
    model_configuration: dict[str, Any]
    baseline_method: str
    original_score: float
    final_score: float
    threshold: float
    decision_flipped: bool
    total_edit_cost: float
    grounding_metrics: GroundingMetrics
    random_seed: int | None = None
    edit_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="All ProposedEdit IDs generated during this session (including rejected)",
    )

    @field_validator("baseline_method")
    @classmethod
    def validate_baseline_method(cls, v: str) -> str:
        allowed = {"original_resume", "generic_llm", "proposed"}
        if v not in allowed:
            raise ValueError(
                f"'{v}' is not a valid baseline_method. "
                f"Allowed values: {', '.join(sorted(allowed))}."
            )
        return v


class ExperimentRunSummary(BaseModel):
    """Six summary fields returned per item in the paginated list."""

    id: uuid.UUID
    baseline_method: str
    original_score: float
    final_score: float
    decision_flipped: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ExperimentRunResponse(BaseModel):
    """Full experiment run record returned by ``GET /api/experiments/{id}``."""

    id: uuid.UUID
    resume_id: uuid.UUID
    job_description_id: uuid.UUID
    model_configuration: dict[str, Any]
    baseline_method: str
    original_score: float
    final_score: float
    threshold: float
    decision_flipped: bool
    total_edit_cost: float
    grounding_metrics: dict[str, float]
    random_seed: int | None
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ProposedEditSummary(BaseModel):
    """Minimal edit info for experiment reports."""

    id: uuid.UUID
    edit_type: str
    original_text: str
    proposed_text: str
    verification_status: str
    edit_cost: float

    model_config = {"from_attributes": True}


class ExperimentReport(BaseModel):
    """Full report returned by ``GET /api/experiments/{id}/report``."""

    run: ExperimentRunResponse
    all_edits: list[ProposedEditSummary]


class PaginatedResult(BaseModel):
    """Wrapper for paginated list endpoints."""

    items: list[ExperimentRunSummary]
    total: int
    page: int
    page_size: int
