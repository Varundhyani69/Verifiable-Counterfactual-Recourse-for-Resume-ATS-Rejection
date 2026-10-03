"""
ResumeDocument ORM model.

Represents an uploaded or manually entered resume. Stores the full
extracted text and character-level source spans so downstream components
can trace every claim back to its origin location (Req 1.2).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base
from backend.app.models.enums import DocumentType
from backend.app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.models.candidate_fact import CandidateFact
    from backend.app.models.resume_version import ResumeVersion


class ResumeDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Stores a candidate's resume in its original extracted form.

    source_spans is a JSONB array of {start, end, text} objects preserving
    character-level offsets for every extracted text segment.
    """

    __tablename__ = "resume_documents"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_type: Mapped[DocumentType] = mapped_column(
        String(10),
        nullable=False,
        doc="One of: pdf, docx, manual",
    )
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_spans: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    # Relationships
    candidate_facts: Mapped[list[CandidateFact]] = relationship(
        "CandidateFact",
        back_populates="source_document",
        cascade="all, delete-orphan",  # Req 14.6
        passive_deletes=True,
    )
    resume_versions: Mapped[list[ResumeVersion]] = relationship(
        "ResumeVersion",
        back_populates="original_resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ResumeDocument id={self.id} type={self.document_type} "
            f"candidate={self.candidate_id}>"
        )
