"""Request and response contracts for job description analysis (Task 7)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.enums import ExtractionType, ImportanceLevel, RequirementType


class JobDescriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=10_000, strict=True)

    @field_validator("text")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Job description text must not be blank.")
        return value


class JobRequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requirement_text: str
    requirement_type: RequirementType
    importance: ImportanceLevel
    extraction_type: ExtractionType
    normalized_skills: list[str]
    source_span: dict[str, int]


class JobDescriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    raw_text: str
    requirements: list[JobRequirementResponse]
    created_at: datetime
