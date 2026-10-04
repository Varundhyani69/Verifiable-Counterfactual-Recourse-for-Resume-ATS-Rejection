"""
API router for recourse generation.

    POST /api/recourse/generate — generate and optimize proposed edits

Requirements: 5.1–5.8, 6.1–6.7
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.response import error_response, success_response
from backend.app.schemas.recourse import (
    OptimizationConfig,
    PartialResult,
    ProposedEditResponse,
    RecourseGenerateRequest,
    RecourseGenerateResponse,
)
from backend.app.services import optimizer as optimizer_svc
from backend.app.services import recourse_engine

router = APIRouter(tags=["recourse"])


@router.post("/recourse/generate")
async def generate_recourse(
    body: RecourseGenerateRequest,
    db: Session = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """
    Generate and optimize counterfactual recourse edits.

    1. Calls the recourse engine to produce ProposedEdit candidates
    2. Calls the optimizer to select the minimal-cost feasible subset
    3. Returns either a feasible recourse set or an infeasible response
       with partial_result and constraints_violated.
    """
    # ── Generate edit candidates ──────────────────────────────────────────
    edits, status, infeasible_reason, infeasible_detail = recourse_engine.generate(
        db=db,
        resume_version_id=body.resume_version_id,
        job_description_id=body.job_description_id,
    )

    if status == "infeasible":
        recourse_id = uuid.uuid4()
        response = RecourseGenerateResponse(
            recourse_id=recourse_id,
            status="infeasible",
            reason=infeasible_reason,
            detail=infeasible_detail,
            constraints_violated=["threshold"],
            partial_result=PartialResult(
                edits=[],
                total_edit_cost=0.0,
                projected_score=0.0,
            ),
        )
        return success_response(response.model_dump(mode="json"), status_code=201)  # type: ignore[return-value]

    # ── Fetch supporting data for optimizer ───────────────────────────────
    from sqlalchemy import select
    from backend.app.models.candidate_fact import CandidateFact
    from backend.app.models.enums import VerificationStatus
    from backend.app.models.job_requirement import JobRequirement
    from backend.app.models.resume_version import ResumeVersion

    resume_version = db.get(ResumeVersion, body.resume_version_id)
    if resume_version is None:
        return error_response("NOT_FOUND", "ResumeVersion not found.", status_code=404)  # type: ignore[return-value]

    candidate_id = resume_version.original_resume.candidate_id
    usable_facts = list(
        db.execute(
            select(CandidateFact).where(
                CandidateFact.candidate_id == candidate_id,
                CandidateFact.verification_status != VerificationStatus.UNSUPPORTED,
            )
        ).scalars().all()
    )

    jd_requirements = list(
        db.execute(
            select(JobRequirement).where(
                JobRequirement.job_description_id == body.job_description_id
            )
        ).scalars().all()
    )

    jd_skills = [
        skill
        for req in jd_requirements
        for skill in req.normalized_skills
    ]

    # ── Run optimizer ─────────────────────────────────────────────────────
    config = body.optimization_config
    opt_result = optimizer_svc.optimize(
        db=db,
        edits=edits,
        resume_version=resume_version,
        usable_facts=usable_facts,
        jd_requirement_skills=jd_skills,
        config=config,
    )

    recourse_id = uuid.uuid4()

    if opt_result.status == "infeasible":
        # Build partial result
        partial_edits = [
            ProposedEditResponse(
                id=e.id,
                original_text=e.original_text,
                proposed_text=e.proposed_text,
                edit_type=str(e.edit_type.value) if hasattr(e.edit_type, "value") else str(e.edit_type),
                evidence_fact_ids=[f.id for f in e.evidence_facts],
                job_requirement_ids=[r.id for r in e.job_requirements],
                verification_status=str(e.verification_status.value) if hasattr(e.verification_status, "value") else str(e.verification_status),
                edit_cost=e.edit_cost,
                score_contribution=e.score_contribution,
            )
            for e in (opt_result.partial_result.edits if opt_result.partial_result else [])
        ]
        partial = PartialResult(
            edits=partial_edits,
            total_edit_cost=opt_result.partial_result.total_edit_cost if opt_result.partial_result else 0.0,
            projected_score=opt_result.partial_result.projected_score if opt_result.partial_result else 0.0,
        )
        response = RecourseGenerateResponse(
            recourse_id=recourse_id,
            status="infeasible",
            reason="threshold",
            detail="No subset of edits could cross the ATS threshold while satisfying all constraints.",
            constraints_violated=opt_result.constraints_violated,
            partial_result=partial,
        )
        return success_response(response.model_dump(mode="json"), status_code=201)  # type: ignore[return-value]

    # ── Build feasible response ───────────────────────────────────────────
    accepted_edit_responses = [
        ProposedEditResponse(
            id=e.id,
            original_text=e.original_text,
            proposed_text=e.proposed_text,
            edit_type=str(e.edit_type.value) if hasattr(e.edit_type, "value") else str(e.edit_type),
            evidence_fact_ids=[f.id for f in e.evidence_facts],
            job_requirement_ids=[r.id for r in e.job_requirements],
            verification_status=str(e.verification_status.value) if hasattr(e.verification_status, "value") else str(e.verification_status),
            edit_cost=e.edit_cost,
            score_contribution=e.score_contribution,
        )
        for e in opt_result.accepted_edits
    ]

    response = RecourseGenerateResponse(
        recourse_id=recourse_id,
        status="feasible",
        accepted_edits=accepted_edit_responses,
        total_edit_cost=opt_result.total_edit_cost,
        projected_score=opt_result.projected_score,
        projected_decision=opt_result.projected_decision,  # type: ignore[arg-type]
    )
    return success_response(response.model_dump(mode="json"), status_code=201)  # type: ignore[return-value]
