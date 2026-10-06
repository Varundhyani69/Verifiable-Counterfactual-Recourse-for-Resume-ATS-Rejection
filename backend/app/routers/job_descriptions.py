"""Job description creation and retrieval endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.response import success_response
from backend.app.schemas.job_description import JobDescriptionRequest, JobDescriptionResponse
from backend.app.services import jd_analyzer

router = APIRouter(tags=["job-descriptions"])


@router.post("/job-descriptions")
def create_job_description(
    body: JobDescriptionRequest, db: Session = Depends(get_db)
) -> JSONResponse:
    jd, requirements = jd_analyzer.analyze(db=db, jd_text=body.text)
    payload = JobDescriptionResponse.model_validate(jd).model_dump(mode="json")
    warning = (
        "No requirements were extracted from this job description." if not requirements else None
    )
    payload["warning"] = warning
    if warning:
        # Req 2.7 asks for a top-level warning; design.md also shows data.warning.
        return JSONResponse(content={"data": payload, "warning": warning}, status_code=201)
    return success_response(payload, status_code=201)


@router.get("/job-descriptions/{jd_id}")
def get_job_description(jd_id: uuid.UUID, db: Session = Depends(get_db)) -> JSONResponse:
    jd = jd_analyzer.get_jd(db=db, jd_id=jd_id)
    return success_response(JobDescriptionResponse.model_validate(jd).model_dump(mode="json"))
