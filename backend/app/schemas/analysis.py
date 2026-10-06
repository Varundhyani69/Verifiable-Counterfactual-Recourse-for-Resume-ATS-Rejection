"""
Pydantic schemas for the ATS analysis endpoint.

Covers:
- AnalysisRequest  — POST /api/analysis request body
- ScoreBreakdown   — nested sub-scores
- AnalysisResponse — POST /api/analysis response

Requirements: 4.1–4.9
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ScoringConfigRequest(BaseModel):
    """
    ATS scoring weights embedded in the analysis request.

    skill_overlap_weight + sbert_weight must equal 1.0 (±1e-9).
    threshold must be in [0.0, 1.0].
    """

    skill_overlap_weight: float = Field(0.5, ge=0.0, le=1.0)
    sbert_weight: float = Field(0.5, ge=0.0, le=1.0)
    threshold: float = Field(0.5, ge=0.0, le=1.0)
    sbert_model_name: str = Field("all-MiniLM-L6-v2")

    @model_validator(mode="after")
    def weights_must_sum_to_one(self) -> "ScoringConfigRequest":
        total = self.skill_overlap_weight + self.sbert_weight
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"skill_overlap_weight + sbert_weight must equal 1.0; got {total:.9f}."
            )
        return self


class AnalysisRequest(BaseModel):
    """Request body for POST /api/analysis."""

    resume_id: uuid.UUID
    job_description_id: uuid.UUID
    scoring_config: ScoringConfigRequest = Field(
        default_factory=ScoringConfigRequest
    )


class ScoreBreakdown(BaseModel):
    """Nested score breakdown in the analysis response."""

    total_score: float
    skill_overlap_score: float
    semantic_similarity_score: float
    weights: dict[str, float]
    threshold: float


class AnalysisResponse(BaseModel):
    """Response body for POST /api/analysis."""

    resume_version_id: uuid.UUID
    version_number: int
    score_breakdown: ScoreBreakdown
    decision: Literal["pass", "fail"]
    disclosure: str


class VerificationReportResponse(BaseModel):
    """JSON representation of a single VerificationReport."""

    edit_id: uuid.UUID
    methods_used: list[str]
    evidence_fact_ids: list[uuid.UUID]
    assigned_status: str
    entailment_score: float
    rationale: str


class VerifyResponse(BaseModel):
    """Response body for POST /api/recourse/{id}/verify."""

    resume_version_id: uuid.UUID
    verification_reports: list[VerificationReportResponse]


class ExplanationCardResponse(BaseModel):
    """JSON representation of a single ExplanationCard."""

    edit_id: uuid.UUID
    prose_description: str
    ats_improvement_reason: str
    evidence_fact_ids: list[uuid.UUID]
    evidence_claim_texts: list[str]
    job_requirement_ids: list[uuid.UUID]
    requirement_texts: list[str]
    score_contribution: float
    edit_cost: float
    verification_status: str
    edit_type: str
    original_text: str
    proposed_text: str
    can_confirm: bool
    can_reject: bool


class AggregateMetricsResponse(BaseModel):
    """JSON representation of AggregateMetrics."""

    total_edit_cost: float
    projected_final_score: float | None
    projected_decision: str | None
    overall_grounding_rate: float
    unsupported_claim_rate: float


class EditStatusUpdateRequest(BaseModel):
    """Request body for PATCH /api/recourse/edits/{edit_id}/status."""

    action: Literal["confirm", "reject"]


class EditStatusUpdateResponse(BaseModel):
    """Response body for PATCH /api/recourse/edits/{edit_id}/status."""

    edit_id: uuid.UUID
    verification_status: str
    action_applied: str
