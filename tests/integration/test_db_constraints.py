"""Database-level constraint tests using direct SQLAlchemy sessions.
(Task 17 — Yash)
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.exceptions import ImmutableRecordError
from backend.app.models.candidate_fact import CandidateFact
from backend.app.models.enums import ClaimType, VerificationStatus
from backend.app.models.experiment_run import ExperimentRun
from backend.app.models.resume_version import ResumeVersion
from tests.yash_support import (
    make_session,
    seed_job_description,
    seed_resume,
    seed_resume_version,
)


def test_fk_cascade_delete_resume_deletes_facts():
    """Deleting a ResumeDocument cascades to CandidateFact rows."""
    db = make_session()
    try:
        resume = seed_resume(db)
        candidate_id = resume.candidate_id

        facts = [
            CandidateFact(
                id=uuid.uuid4(),
                candidate_id=candidate_id,
                claim_text=f"Fact {i}",
                original_claim_text=f"Fact {i}",
                claim_type=ClaimType.SKILL,
                source_document_id=resume.id,
                source_span={"start": 0, "end": 6},
                verification_status=VerificationStatus.NEEDS_CONFIRMATION,
                metadata_={},
            )
            for i in range(2)
        ]
        db.add_all(facts)
        db.commit()

        # Ensure FK enforcement is on
        db.execute(text("PRAGMA foreign_keys = ON"))

        # Delete the resume — should cascade to facts
        db.delete(resume)
        db.commit()

        remaining = db.query(CandidateFact).filter_by(candidate_id=candidate_id).all()
        assert len(remaining) == 0
    finally:
        db.close()


def test_unique_constraint_resume_version_number():
    """Inserting two ResumeVersions with same (resume_id, version_number) raises IntegrityError."""
    db = make_session()
    try:
        resume = seed_resume(db)
        db.commit()

        rv1 = ResumeVersion(
            id=uuid.uuid4(),
            original_resume_id=resume.id,
            version_number=1,
            content="v1 content",
        )
        rv2 = ResumeVersion(
            id=uuid.uuid4(),
            original_resume_id=resume.id,
            version_number=1,
            content="duplicate version",
        )
        db.add(rv1)
        db.flush()
        db.add(rv2)

        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.close()


def test_append_only_experiment_raises_immutable_error():
    """Mutating an ExperimentRun after mark_persisted() raises ImmutableRecordError."""
    db = make_session()
    try:
        resume = seed_resume(db)
        jd = seed_job_description(db)
        db.commit()

        run = ExperimentRun(
            id=uuid.uuid4(),
            resume_id=resume.id,
            job_description_id=jd.id,
            model_configuration={"sbert_model": "all-MiniLM-L6-v2"},
            baseline_method="original_resume",
            original_score=0.4,
            final_score=0.72,
            threshold=0.5,
            decision_flipped=True,
            total_edit_cost=0.3,
            grounding_metrics={
                "evidence_grounding_rate": 0.8,
                "unsupported_claim_rate": 0.1,
                "original_fact_preservation_rate": 0.9,
            },
            random_seed=42,
        )
        db.add(run)
        db.flush()

        # Manually mark as persisted (event hook may not fire in test env)
        run.mark_persisted()

        with pytest.raises(ImmutableRecordError):
            run.original_score = 0.99
    finally:
        db.close()
