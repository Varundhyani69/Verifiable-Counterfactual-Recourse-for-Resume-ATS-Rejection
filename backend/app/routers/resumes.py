"""
API router for resume ingestion endpoints.

    POST /api/resumes/upload   — upload a PDF or DOCX file
    POST /api/resumes/manual   — submit manually typed resume text
    GET  /api/resumes/{id}     — retrieve a resume document

Requirements: 1.1–1.12
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.response import success_response
from backend.app.schemas.ingestion import ManualIngestionRequest, ResumeDocumentResponse
from backend.app.services import evidence_extractor, ingestion_service

router = APIRouter(tags=["resumes"])


@router.post("/resumes/upload")
async def upload_resume(
    file: UploadFile = File(...),
    candidate_id: uuid.UUID = Form(...),
    db: Session = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """
    Ingest a PDF or DOCX resume file.

    Automatically triggers evidence extraction on success.
    """
    file_data = await file.read()
    resume = ingestion_service.ingest_file(
        db=db,
        file_data=file_data,
        filename=file.filename or "unknown",
        content_type=file.content_type or "application/octet-stream",
        candidate_id=candidate_id,
    )

    # Auto-trigger evidence extraction (Task 5 → Task 6 integration)
    evidence_extractor.extract(db=db, resume=resume)

    doc_response = ResumeDocumentResponse.model_validate(resume)
    return success_response(doc_response.model_dump(mode="json"), status_code=201)  # type: ignore[return-value]


@router.post("/resumes/manual")
async def manual_resume(
    body: ManualIngestionRequest,
    db: Session = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """
    Ingest manually entered resume text (1–50,000 chars).

    Automatically triggers evidence extraction on success.
    """
    resume = ingestion_service.ingest_manual(
        db=db,
        text=body.text,
        candidate_id=body.candidate_id,
    )

    # Auto-trigger evidence extraction
    evidence_extractor.extract(db=db, resume=resume)

    doc_response = ResumeDocumentResponse.model_validate(resume)
    return success_response(doc_response.model_dump(mode="json"), status_code=201)  # type: ignore[return-value]


@router.get("/resumes/{resume_id}")
async def get_resume(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """Retrieve a resume document by ID."""
    resume = ingestion_service.get_resume(db=db, resume_id=resume_id)
    doc_response = ResumeDocumentResponse.model_validate(resume)
    return success_response(doc_response.model_dump(mode="json"))  # type: ignore[return-value]
