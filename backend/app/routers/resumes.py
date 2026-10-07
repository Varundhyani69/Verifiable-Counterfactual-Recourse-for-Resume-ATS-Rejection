"""
API router for resume ingestion and export endpoints.

    POST /api/resumes/upload                         — upload a PDF or DOCX file
    POST /api/resumes/manual                         — submit manually typed resume text
    GET  /api/resumes/versions/{version_id}/download — download a resume version as txt or PDF
    GET  /api/resumes/{id}                           — retrieve a resume document

Note: /resumes/versions/... is registered BEFORE /resumes/{id} so FastAPI
does not greedily match "versions" as a resume_id UUID (it won't parse, but
ordering makes intent explicit and avoids any future ambiguity).

Requirements: 1.1–1.12, 9.3, 9.4
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.resume_version import ResumeVersion
from backend.app.response import error_response, success_response
from backend.app.schemas.ingestion import ManualIngestionRequest, ResumeDocumentResponse
from backend.app.services import evidence_extractor, export_service, ingestion_service

router = APIRouter(tags=["resumes"])


# ── POST /api/resumes/upload ──────────────────────────────────────────────────

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


# ── POST /api/resumes/manual ──────────────────────────────────────────────────

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


# ── GET /api/resumes/versions/{version_id}/download ──────────────────────────
# MUST be registered before GET /resumes/{resume_id} to avoid the wildcard
# route consuming the literal path segment "versions".

@router.get("/resumes/versions/{version_id}/download")
async def download_resume_version(
    version_id: uuid.UUID,
    format: str = Query("txt", pattern="^(txt|pdf)$"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Download a ResumeVersion as plain text or PDF.

    Query parameter:
        format — "txt" (default) or "pdf"

    Returns a file stream with Content-Disposition header, or a JSON 404 if
    the version is not found.

    Requirements: 9.3, 9.4
    """
    version = db.get(ResumeVersion, version_id)
    if version is None:
        return error_response(  # type: ignore[return-value]
            "NOT_FOUND",
            f"ResumeVersion '{version_id}' not found.",
            status_code=404,
        )

    if format == "pdf":
        file_bytes = export_service.export_pdf(version)
        media_type = "application/pdf"
        filename = f"resume_v{version.version_number}.pdf"
    else:
        file_bytes = export_service.export_txt(version)
        media_type = "text/plain; charset=utf-8"
        filename = f"resume_v{version.version_number}.txt"

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── GET /api/resumes/{resume_id} ──────────────────────────────────────────────

@router.get("/resumes/{resume_id}")
async def get_resume(
    resume_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """Retrieve a resume document by ID."""
    resume = ingestion_service.get_resume(db=db, resume_id=resume_id)
    doc_response = ResumeDocumentResponse.model_validate(resume)
    return success_response(doc_response.model_dump(mode="json"))  # type: ignore[return-value]
