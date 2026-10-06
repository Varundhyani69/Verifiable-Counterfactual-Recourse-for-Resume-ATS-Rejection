"""Candidate-scoped evidence retrieval and audited updates (Requirements 3.4–3.9)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.exceptions import ResourceNotFoundError
from backend.app.models.candidate_fact import CandidateFact
from backend.app.models.enums import VerificationStatus
from backend.app.models.resume_document import ResumeDocument
from backend.app.schemas.evidence import CandidateFactPatch


class EvidenceBank:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_facts(self, candidate_id: uuid.UUID) -> list[CandidateFact]:
        facts = list(
            self.db.scalars(
                select(CandidateFact)
                .where(CandidateFact.candidate_id == candidate_id)
                .order_by(CandidateFact.created_at, CandidateFact.id)
            )
        )
        # There is no Candidate table: an ingested document establishes candidate existence.
        if (
            not facts
            and self.db.scalar(
                select(ResumeDocument.id)
                .where(ResumeDocument.candidate_id == candidate_id)
                .limit(1)
            )
            is None
        ):
            raise ResourceNotFoundError("Candidate", str(candidate_id))
        return facts

    def get_usable_facts(self, candidate_id: uuid.UUID) -> list[CandidateFact]:
        return [
            fact
            for fact in self.get_facts(candidate_id)
            if fact.verification_status != VerificationStatus.UNSUPPORTED
        ]

    def update_fact(
        self, candidate_id: uuid.UUID, fact_id: uuid.UUID, patch: CandidateFactPatch
    ) -> CandidateFact:
        # Revalidate even service-level callers before touching a stored record.
        patch = CandidateFactPatch.model_validate(patch.model_dump(exclude_unset=True))
        fact = self.db.scalar(
            select(CandidateFact).where(
                CandidateFact.id == fact_id, CandidateFact.candidate_id == candidate_id
            )
        )
        if fact is None:
            raise ResourceNotFoundError("CandidateFact", str(fact_id))
        try:
            for name, value in patch.model_dump(exclude_unset=True).items():
                setattr(fact, name, value)
            fact.updated_at = datetime.now(UTC)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(fact)
        return fact


def get_facts(db: Session, candidate_id: uuid.UUID) -> list[CandidateFact]:
    return EvidenceBank(db).get_facts(candidate_id)


def get_usable_facts(db: Session, candidate_id: uuid.UUID) -> list[CandidateFact]:
    return EvidenceBank(db).get_usable_facts(candidate_id)


def update_fact(
    db: Session, candidate_id: uuid.UUID, fact_id: uuid.UUID, patch: CandidateFactPatch
) -> CandidateFact:
    return EvidenceBank(db).update_fact(candidate_id, fact_id, patch)
