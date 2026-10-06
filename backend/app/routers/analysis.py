"""
API router for the ATS scoring endpoint.

    POST /api/analysis — score a resume version against a job description

Requirements: 4.1–4.9
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.response import error_response, success_response
from backend.app.schemas.analysis import (
    AnalysisRequest,
    AnalysisResponse,
    ScoreBreakdown,
)
from backend.app.services.ats_scorer import ScoringConfig, score as ats_score

router = APIRouter(tags=["analysis"])


@router.post("/analysis")
async def create_analysis(
    body: AnalysisRequest,
    db: Session = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """
    Score a resume against a job description and persist the result.

    1. Validates resume_id and job_description_id exist.
    2. Calls the ATS scorer.
    3. Stores the result as a new ResumeVersion (version_number = 1 for
       the baseline; subsequent versions increment by 1).
    4. Returns score breakdown, decision, and disclosure string.
    """
    from backend.app.models.job_description import JobDescription
    from backend.app.models.resume_document import ResumeDocument
    from backend.app.models.resume_version import ResumeVersion

    # ── Validate resume exists ────────────────────────────────────────────
    resume = db.get(ResumeDocument, body.resume_id)
    if resume is None:
        return error_response(  # type: ignore[return-value]
            "NOT_FOUND",
            f"ResumeDocument '{body.resume_id}' not found.",
            status_code=404,
        )

    # ── Validate JD exists ────────────────────────────────────────────────
    jd = db.get(JobDescription, body.job_description_id)
    if jd is None:
        return error_response(  # type: ignore[return-value]
            "NOT_FOUND",
            f"JobDescription '{body.job_description_id}' not found.",
            status_code=404,
        )

    # ── Run ATS scorer ────────────────────────────────────────────────────
    cfg = ScoringConfig(
        skill_overlap_weight=body.scoring_config.skill_overlap_weight,
        sbert_weight=body.scoring_config.sbert_weight,
        threshold=body.scoring_config.threshold,
        sbert_model_name=body.scoring_config.sbert_model_name,
    )

    try:
        result = ats_score(
            resume_text=resume.extracted_text,
            jd_text=jd.raw_text,
            config=cfg,
        )
    except RuntimeError as exc:
        # SBERT model failure → HTTP 502
        return error_response(  # type: ignore[return-value]
            "SBERT_FAILURE",
            str(exc),
            status_code=502,
        )

    # ── Determine version number ──────────────────────────────────────────
    max_version: int | None = db.execute(
        select(func.max(ResumeVersion.version_number)).where(
            ResumeVersion.original_resume_id == body.resume_id
        )
    ).scalar()

    version_number = 1 if max_version is None else max_version + 1

    # ── Persist ResumeVersion ─────────────────────────────────────────────
    rv = ResumeVersion(
        id=uuid.uuid4(),
        original_resume_id=body.resume_id,
        version_number=version_number,
        content=resume.extracted_text,
        ats_score=result.total_score,
        decision=result.decision,  # type: ignore[arg-type]
    )
    db.add(rv)
    db.flush()

    # ── Build response ────────────────────────────────────────────────────
    response = AnalysisResponse(
        resume_version_id=rv.id,
        version_number=rv.version_number,
        score_breakdown=ScoreBreakdown(
            total_score=result.total_score,
            skill_overlap_score=result.skill_overlap_score,
            semantic_similarity_score=result.semantic_similarity_score,
            weights=result.weights,
            threshold=result.threshold,
        ),
        decision=result.decision,
        disclosure=result.disclosure,
    )
    return success_response(response.model_dump(mode="json"), status_code=201)  # type: ignore[return-value]
