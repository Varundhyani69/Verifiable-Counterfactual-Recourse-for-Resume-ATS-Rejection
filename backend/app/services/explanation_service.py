"""
Explanation Service.

Builds human-readable ExplanationCards and AggregateMetrics from verified
ProposedEdit records.

ExplanationCard (7 required fields per Req 8.1):
  1. prose_description      — natural-language description of the edit
  2. ats_improvement_reason — why this change improves the ATS score
  3. evidence_fact_ids      — UUIDs of grounding CandidateFacts
  4. evidence_claim_texts   — the claim_text for each grounding fact
  5. job_requirement_ids    — UUIDs of the addressed JobRequirements
  6. requirement_texts      — the requirement_text for each addressed req
  7. score_contribution     — estimated ATS score delta from this edit
  + edit_cost               — composite cost [0.0, 1.0]
  + verification_status     — current status string

AggregateMetrics (Req 8.3):
  - total_edit_cost
  - projected_final_score
  - projected_decision
  - overall_grounding_rate
  - unsupported_claim_rate

Confirm / Reject actions (Req 8.5, 8.6):
  - Confirm: Needs Confirmation → Supported
  - Reject:  Needs Confirmation → Unsupported (NO regeneration)

Public API:
    build_card(edit, facts, requirements) → ExplanationCard
    build_aggregate(accepted_edits)       → AggregateMetrics
    confirm_edit(db, edit_id)             → ProposedEdit
    reject_edit(db, edit_id)              → ProposedEdit

Requirements: 8.1–8.6
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.exceptions import ResourceNotFoundError
from backend.app.models.candidate_fact import CandidateFact
from backend.app.models.enums import VerificationStatus
from backend.app.models.job_requirement import JobRequirement
from backend.app.models.proposed_edit import ProposedEdit

# ── Pydantic data models ──────────────────────────────────────────────────────


class ExplanationCard(BaseModel):
    """
    Human-readable explanation for a single accepted ProposedEdit.

    All 7 required fields must be non-null (Property 20).
    """

    edit_id: uuid.UUID

    # Field 1
    prose_description: str
    # Field 2
    ats_improvement_reason: str
    # Fields 3 & 4
    evidence_fact_ids: list[uuid.UUID]
    evidence_claim_texts: list[str]
    # Fields 5 & 6
    job_requirement_ids: list[uuid.UUID]
    requirement_texts: list[str]
    # Field 7
    score_contribution: float

    # Additional fields (not counted in the "7 required" but always present)
    edit_cost: float
    verification_status: str
    edit_type: str
    original_text: str
    proposed_text: str

    # Confirm/Reject controls are present only for Needs Confirmation edits (Req 8.4)
    can_confirm: bool = False
    can_reject: bool = False


class AggregateMetrics(BaseModel):
    """
    Summary metrics across all accepted edits (Req 8.3).
    """

    total_edit_cost: float
    projected_final_score: float | None
    projected_decision: Literal["pass", "fail"] | None
    overall_grounding_rate: float  # fraction of edits that are Supported / PartiallySupported
    unsupported_claim_rate: float  # fraction of edits that are Unsupported


# ── Card builder ──────────────────────────────────────────────────────────────

_EDIT_TYPE_DESCRIPTIONS: dict[str, str] = {
    "rephrase": (
        "Rephrase this claim to more clearly reflect a relevant skill or experience."
    ),
    "surface_qualification": (
        "Surface a buried qualification to a more prominent position in the resume."
    ),
    "reorder": (
        "Reorder bullet points to place the most JD-relevant item first."
    ),
    "normalize_terminology": (
        "Replace an informal skill alias with its canonical industry-standard name."
    ),
    "reorganize_sections": (
        "Move a high-relevance section earlier in the resume."
    ),
    "remove_redundancy": (
        "Remove a redundant claim that duplicates another entry in the same section."
    ),
}

_EDIT_TYPE_ATS_REASON: dict[str, str] = {
    "rephrase": (
        "A clearer skill mention increases token overlap with job requirements and "
        "may improve the semantic similarity component of the ATS score."
    ),
    "surface_qualification": (
        "Placing this qualification prominently increases the likelihood that an "
        "ATS scanner will recognise it as a matched requirement."
    ),
    "reorder": (
        "Leading with the most requirement-relevant bullet improves early-scan "
        "keyword density, boosting the skill-overlap score."
    ),
    "normalize_terminology": (
        "Using the canonical skill name (as it appears in the job description) "
        "increases exact-match skill overlap."
    ),
    "reorganize_sections": (
        "Moving a highly relevant section earlier improves the effective keyword "
        "density in the portion of the resume most likely to be parsed first."
    ),
    "remove_redundancy": (
        "Removing redundant claims tightens the resume and can slightly improve "
        "the semantic coherence score."
    ),
}


def build_card(
    edit: ProposedEdit,
    facts: list[CandidateFact],
    requirements: list[JobRequirement],
) -> ExplanationCard:
    """
    Build an ExplanationCard for a single ProposedEdit.

    Args:
        edit:         The ProposedEdit to explain.
        facts:        Grounding CandidateFacts linked to this edit.
        requirements: Addressed JobRequirements linked to this edit.

    Returns:
        ExplanationCard with all 7 required fields non-null.

    Requirements: 8.1, 8.2
    """
    edit_type_str = (
        edit.edit_type.value
        if hasattr(edit.edit_type, "value")
        else str(edit.edit_type)
    )

    prose = _EDIT_TYPE_DESCRIPTIONS.get(
        edit_type_str,
        f"Apply a '{edit_type_str}' edit to improve ATS alignment.",
    )
    ats_reason = _EDIT_TYPE_ATS_REASON.get(
        edit_type_str,
        "This change is expected to improve keyword overlap or semantic similarity.",
    )

    status_str = (
        edit.verification_status.value
        if hasattr(edit.verification_status, "value")
        else str(edit.verification_status)
    )

    is_needs_confirmation = (
        status_str == VerificationStatus.NEEDS_CONFIRMATION.value
    )

    return ExplanationCard(
        edit_id=edit.id,
        prose_description=prose,
        ats_improvement_reason=ats_reason,
        evidence_fact_ids=[f.id for f in facts],
        evidence_claim_texts=[f.claim_text for f in facts],
        job_requirement_ids=[r.id for r in requirements],
        requirement_texts=[r.requirement_text for r in requirements],
        score_contribution=edit.score_contribution,
        edit_cost=edit.edit_cost,
        verification_status=status_str,
        edit_type=edit_type_str,
        original_text=edit.original_text,
        proposed_text=edit.proposed_text,
        can_confirm=is_needs_confirmation,
        can_reject=is_needs_confirmation,
    )


# ── Aggregate metrics ─────────────────────────────────────────────────────────


def build_aggregate(
    accepted_edits: list[ProposedEdit],
    projected_final_score: float | None = None,
    threshold: float | None = None,
) -> AggregateMetrics:
    """
    Compute aggregate metrics across *accepted_edits*.

    Args:
        accepted_edits:       List of accepted ProposedEdit records.
        projected_final_score: Optional ATS score after applying all edits.
        threshold:             Optional ATS decision threshold for pass/fail.

    Returns:
        AggregateMetrics

    Requirements: 8.3
    """
    if not accepted_edits:
        return AggregateMetrics(
            total_edit_cost=0.0,
            projected_final_score=projected_final_score,
            projected_decision=_decision(projected_final_score, threshold),
            overall_grounding_rate=0.0,
            unsupported_claim_rate=0.0,
        )

    total_cost = sum(e.edit_cost for e in accepted_edits)
    n = len(accepted_edits)

    grounded_count = sum(
        1
        for e in accepted_edits
        if _status_value(e) in (
            VerificationStatus.SUPPORTED.value,
            VerificationStatus.PARTIALLY_SUPPORTED.value,
        )
    )
    unsupported_count = sum(
        1
        for e in accepted_edits
        if _status_value(e) == VerificationStatus.UNSUPPORTED.value
    )

    return AggregateMetrics(
        total_edit_cost=total_cost,
        projected_final_score=projected_final_score,
        projected_decision=_decision(projected_final_score, threshold),
        overall_grounding_rate=grounded_count / n,
        unsupported_claim_rate=unsupported_count / n,
    )


def _status_value(edit: ProposedEdit) -> str:
    return (
        edit.verification_status.value
        if hasattr(edit.verification_status, "value")
        else str(edit.verification_status)
    )


def _decision(
    score: float | None, threshold: float | None
) -> Literal["pass", "fail"] | None:
    if score is None or threshold is None:
        return None
    return "pass" if score >= threshold else "fail"


# ── Confirm / Reject actions ──────────────────────────────────────────────────


def confirm_edit(*, db: Session, edit_id: uuid.UUID) -> ProposedEdit:
    """
    Confirm a Needs Confirmation edit → set status to Supported.

    Args:
        db:      Active SQLAlchemy session.
        edit_id: UUID of the ProposedEdit to confirm.

    Returns:
        Updated ProposedEdit.

    Raises:
        ResourceNotFoundError: edit not found.
        ValueError: edit is not in Needs Confirmation status.

    Requirements: 8.5
    """
    edit = db.get(ProposedEdit, edit_id)
    if edit is None:
        raise ResourceNotFoundError("ProposedEdit", str(edit_id))

    current = _status_value(edit)
    if current != VerificationStatus.NEEDS_CONFIRMATION.value:
        raise ValueError(
            f"Only 'Needs Confirmation' edits can be confirmed; "
            f"current status is '{current}'."
        )

    edit.verification_status = VerificationStatus.SUPPORTED  # type: ignore[assignment]
    db.flush()
    return edit


def reject_edit(*, db: Session, edit_id: uuid.UUID) -> ProposedEdit:
    """
    Reject a Needs Confirmation edit → set status to Unsupported.

    Rejection does NOT trigger recourse regeneration (Req 8.6).

    Args:
        db:      Active SQLAlchemy session.
        edit_id: UUID of the ProposedEdit to reject.

    Returns:
        Updated ProposedEdit.

    Raises:
        ResourceNotFoundError: edit not found.
        ValueError: edit is not in Needs Confirmation status.

    Requirements: 8.6
    """
    edit = db.get(ProposedEdit, edit_id)
    if edit is None:
        raise ResourceNotFoundError("ProposedEdit", str(edit_id))

    current = _status_value(edit)
    if current != VerificationStatus.NEEDS_CONFIRMATION.value:
        raise ValueError(
            f"Only 'Needs Confirmation' edits can be rejected; "
            f"current status is '{current}'."
        )

    edit.verification_status = VerificationStatus.UNSUPPORTED  # type: ignore[assignment]
    db.flush()
    # NOTE: Intentionally NO regeneration signal here (Req 8.6)
    return edit
