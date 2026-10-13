"""Database and NLP fixtures shared by Yash's API and DB-constraint tests."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, MetaData, Text, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.models.candidate_fact import CandidateFact
from backend.app.models.enums import (
    ATSDecision,
    ClaimType,
    DocumentType,
    VerificationStatus,
)
from backend.app.models.experiment_run import ExperimentRun, experiment_run_edits
from backend.app.models.job_description import JobDescription
from backend.app.models.job_requirement import JobRequirement
from backend.app.models.proposed_edit import (
    ProposedEdit,
    proposed_edit_facts,
    proposed_edit_requirements,
)
from backend.app.models.resume_document import ResumeDocument
from backend.app.models.resume_version import ResumeVersion
from backend.app.services.ats_scorer import DISCLOSURE, ScoreResult


def make_session() -> Session:
    """Create an in-memory SQLite session with all required tables."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()

    # Translate ORM tables to SQLite-compatible DDL
    for model in (
        ResumeDocument,
        CandidateFact,
        JobDescription,
        JobRequirement,
        ResumeVersion,
        ProposedEdit,
        ExperimentRun,
    ):
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            if column.server_default is not None and "gen_random_uuid" in str(
                column.server_default.arg
            ):
                column.server_default = None

    # Also register the junction tables
    proposed_edit_facts.to_metadata(metadata)
    proposed_edit_requirements.to_metadata(metadata)
    experiment_run_edits.to_metadata(metadata)

    metadata.create_all(engine)

    db = Session(engine)
    # Enable FK enforcement for SQLite cascade tests
    db.execute(text("PRAGMA foreign_keys = ON"))
    return db


def seed_resume(
    db: Session,
    candidate_id: uuid.UUID | None = None,
    text_content: str = "Python developer",
) -> ResumeDocument:
    """Insert and return a minimal ResumeDocument."""
    if candidate_id is None:
        candidate_id = uuid.uuid4()
    resume = ResumeDocument(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        document_type=DocumentType.MANUAL,
        filename=None,
        extracted_text=text_content,
        source_spans=[],
    )
    db.add(resume)
    db.flush()
    return resume


def seed_job_description(
    db: Session,
    text_content: str = "Python required",
) -> JobDescription:
    """Insert and return a minimal JobDescription."""
    jd = JobDescription(
        id=uuid.uuid4(),
        raw_text=text_content,
        requirements=[],
    )
    db.add(jd)
    db.flush()
    return jd


def seed_resume_version(
    db: Session,
    resume: ResumeDocument,
    version_number: int = 1,
    score: float = 0.4,
    decision: str = "fail",
) -> ResumeVersion:
    """Insert and return a ResumeVersion linked to the given resume."""
    rv = ResumeVersion(
        id=uuid.uuid4(),
        original_resume_id=resume.id,
        version_number=version_number,
        content=resume.extracted_text,
        ats_score=score,
        decision=ATSDecision.FAIL if decision == "fail" else ATSDecision.PASS,
    )
    db.add(rv)
    db.flush()
    return rv


def mock_score_result() -> ScoreResult:
    """Return a fixed ScoreResult for mocking the ATS scorer."""
    return ScoreResult(
        total_score=0.72,
        skill_overlap_score=0.6,
        semantic_similarity_score=0.84,
        weights={"skill_overlap": 0.5, "sbert": 0.5},
        threshold=0.5,
        decision="pass",
        disclosure=DISCLOSURE,
    )
