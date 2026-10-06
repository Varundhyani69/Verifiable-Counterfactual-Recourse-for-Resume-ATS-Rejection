"""Real database and NLP fixtures shared by Dhruv's service tests."""

import uuid

try:
    import spacy
    _SPACY_AVAILABLE = True
except ImportError:
    spacy = None  # type: ignore[assignment]
    _SPACY_AVAILABLE = False
from sqlalchemy import JSON, MetaData, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.models.candidate_fact import CandidateFact
from backend.app.models.enums import ClaimType, DocumentType, VerificationStatus
from backend.app.models.job_description import JobDescription
from backend.app.models.job_requirement import JobRequirement
from backend.app.models.resume_document import ResumeDocument


def make_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata = MetaData()
    # Translate only the test DDL; production ORM and PostgreSQL schema stay intact.
    for model in (ResumeDocument, CandidateFact, JobDescription, JobRequirement):
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            if column.server_default is not None and "gen_random_uuid" in str(
                column.server_default.arg
            ):
                column.server_default = None
    metadata.create_all(engine)
    return Session(engine)


def make_nlp():
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    ruler = nlp.add_pipe("entity_ruler")
    ruler.add_patterns([{"label": "SKILL", "pattern": "Zig"}])
    return nlp


def seed_evidence(db, statuses=(VerificationStatus.NEEDS_CONFIRMATION,)):
    candidate_id = uuid.uuid4()
    resume = ResumeDocument(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        document_type=DocumentType.MANUAL,
        filename=None,
        extracted_text="Developed Python APIs.",
        source_spans=[{"start": 0, "end": 22}],
    )
    db.add(resume)
    db.flush()
    facts = [
        CandidateFact(
            id=uuid.uuid4(),
            candidate_id=candidate_id,
            claim_text="Developed Python APIs.",
            original_claim_text="Developed Python APIs.",
            claim_type=ClaimType.SKILL,
            source_document_id=resume.id,
            source_span={"start": 0, "end": 22},
            verification_status=status,
            metadata_={"skills": ["Python"], "projects": ["API"]},
        )
        for status in statuses
    ]
    db.add_all(facts)
    db.commit()
    return candidate_id, facts
