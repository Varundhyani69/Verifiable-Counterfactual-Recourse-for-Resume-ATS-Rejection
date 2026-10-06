"""Candidate evidence review endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.response import success_response
from backend.app.schemas.evidence import CandidateFactPatch, CandidateFactResponse
from backend.app.services import evidence_bank

router = APIRouter(tags=["candidates"])


@router.get("/candidates/{candidate_id}/evidence")
def get_evidence(candidate_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    facts = evidence_bank.get_facts(db=db, candidate_id=candidate_id)
    return success_response(
        {
            "candidate_id": str(candidate_id),
            "facts": [
                CandidateFactResponse.model_validate(fact).model_dump(mode="json")
                for fact in facts
            ],
        }
    )


@router.patch("/candidates/{candidate_id}/evidence/{fact_id}")
def patch_evidence(
    candidate_id: uuid.UUID,
    fact_id: uuid.UUID,
    body: CandidateFactPatch,
    db: Session = Depends(get_db),
) -> JSONResponse:
    fact = evidence_bank.update_fact(db=db, candidate_id=candidate_id, fact_id=fact_id, patch=body)
    return success_response(CandidateFactResponse.model_validate(fact).model_dump(mode="json"))
