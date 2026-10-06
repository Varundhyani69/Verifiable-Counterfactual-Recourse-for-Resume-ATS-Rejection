"""Evidence review schemas, with a restricted PATCH surface (Task 8)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.models.enums import ClaimType, VerificationStatus


class CandidateFactPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_text: str | None = Field(default=None, min_length=1, max_length=2000, strict=True)
    verification_status: VerificationStatus | None = None

    @field_validator("claim_text")
    @classmethod
    def non_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("claim_text must not be blank.")
        return value

    @model_validator(mode="after")
    def require_changes(self) -> CandidateFactPatch:
        if not self.model_fields_set:
            raise ValueError("Provide claim_text and/or verification_status.")
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} must not be null.")
        return self


class CandidateFactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    candidate_id: uuid.UUID
    claim_text: str
    original_claim_text: str
    claim_type: ClaimType
    source_document_id: uuid.UUID
    source_span: dict[str, int]
    verification_status: VerificationStatus
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime
