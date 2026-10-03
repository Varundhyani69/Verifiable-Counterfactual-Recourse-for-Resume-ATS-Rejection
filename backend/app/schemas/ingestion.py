"""
Pydantic schemas for resume ingestion.

SourceSpan and ExtractedSegment are the core value objects that flow through
the ingestion pipeline. Response schemas define the JSON shape returned by
the ``POST /api/resumes/upload``, ``POST /api/resumes/manual``, and
``GET /api/resumes/{id}`` endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SourceSpan(BaseModel):
    """Character-level byte-offset span inside extracted text."""

    start: int = Field(..., ge=0, description="Inclusive start offset")
    end: int = Field(..., gt=0, description="Exclusive end offset")


class ExtractedSegment(BaseModel):
    """A contiguous block of text with its character offsets."""

    text: str
    span: SourceSpan


class ManualIngestionRequest(BaseModel):
    """Request body for ``POST /api/resumes/manual``."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="Manual resume text (1–50,000 characters)",
    )
    candidate_id: uuid.UUID


class ResumeDocumentResponse(BaseModel):
    """Response schema for a persisted ResumeDocument."""

    id: uuid.UUID
    candidate_id: uuid.UUID
    filename: str | None
    document_type: str
    extracted_text: str
    source_spans: list[dict[str, int | str]]
    created_at: datetime

    model_config = {"from_attributes": True}
