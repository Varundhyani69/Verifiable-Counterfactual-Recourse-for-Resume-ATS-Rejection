"""
Unit tests for ORM model integrity constraints and invariants.

Tests covered:
  - All model imports resolve without error
  - Enum values are correct strings
  - AppendOnlyMixin raises ImmutableRecordError on post-creation mutation
  - VerificationStatus default is NeedsConfirmation
  - CandidateFact: original_claim_text field exists
  - ResumeVersion: UniqueConstraint is declared
  - ProposedEdit: junction tables are declared

These tests do NOT require a live database — they verify the ORM model
definitions and Python-level invariants only.
"""

from __future__ import annotations

import pytest

from backend.app.exceptions import ImmutableRecordError
from backend.app.models import (
    CandidateFact,
    ExperimentRun,
    JobDescription,
    JobRequirement,
    ProposedEdit,
    ResumeDocument,
    ResumeVersion,
    experiment_run_edits,
    proposed_edit_facts,
    proposed_edit_requirements,
)
from backend.app.models.enums import (
    BaselineMethod,
    ClaimType,
    EditType,
    ImportanceLevel,
    VerificationStatus,
)

# ── Enum value tests ──────────────────────────────────────────────────────────

class TestVerificationStatusEnum:
    def test_values(self) -> None:
        assert VerificationStatus.SUPPORTED.value == "Supported"
        assert VerificationStatus.PARTIALLY_SUPPORTED.value == "Partially Supported"
        assert VerificationStatus.UNSUPPORTED.value == "Unsupported"
        assert VerificationStatus.NEEDS_CONFIRMATION.value == "Needs Confirmation"

    def test_four_members(self) -> None:
        assert len(VerificationStatus) == 4


class TestClaimTypeEnum:
    def test_all_six_types(self) -> None:
        expected = {"skill", "project", "responsibility", "certification",
                    "experience", "achievement"}
        assert {m.value for m in ClaimType} == expected


class TestEditTypeEnum:
    def test_all_six_types(self) -> None:
        expected = {
            "rephrase", "surface_qualification", "reorder",
            "normalize_terminology", "reorganize_sections", "remove_redundancy",
        }
        assert {m.value for m in EditType} == expected


class TestBaselineMethodEnum:
    def test_three_methods(self) -> None:
        expected = {"original_resume", "generic_llm", "proposed"}
        assert {m.value for m in BaselineMethod} == expected


class TestImportanceLevelEnum:
    def test_two_values(self) -> None:
        assert ImportanceLevel.REQUIRED.value == "required"
        assert ImportanceLevel.PREFERRED.value == "preferred"


# ── AppendOnlyMixin tests ─────────────────────────────────────────────────────

class TestAppendOnlyMixin:
    def test_mutation_raises_after_mark_persisted(self) -> None:
        """AppendOnlyMixin must raise ImmutableRecordError after mark_persisted()."""
        run = ExperimentRun()
        # Before persisting, mutation is allowed
        run.original_score = 0.5

        run.mark_persisted()

        with pytest.raises(ImmutableRecordError):
            run.original_score = 0.9

    def test_mutation_allowed_before_mark_persisted(self) -> None:
        """Before mark_persisted(), any attribute can be set freely."""
        run = ExperimentRun()
        run.original_score = 0.42
        run.final_score = 0.61
        assert run.original_score == 0.42
        assert run.final_score == 0.61

    def test_private_attrs_never_blocked(self) -> None:
        """Private attributes (underscore-prefixed) must always be settable."""
        run = ExperimentRun()
        run.mark_persisted()
        # Should not raise
        run._is_persisted = True  # already true, but must not raise


# ── ORM model structural tests ────────────────────────────────────────────────

class TestResumeDocumentModel:
    def test_tablename(self) -> None:
        assert ResumeDocument.__tablename__ == "resume_documents"

    def test_required_columns_exist(self) -> None:
        cols = {c.name for c in ResumeDocument.__table__.columns}
        for col in ("id", "candidate_id", "filename", "document_type",
                    "extracted_text", "source_spans", "created_at"):
            assert col in cols, f"Missing column: {col}"


class TestCandidateFactModel:
    def test_tablename(self) -> None:
        assert CandidateFact.__tablename__ == "candidate_facts"

    def test_original_claim_text_column_exists(self) -> None:
        """original_claim_text must be a dedicated column (not alias of claim_text)."""
        cols = {c.name for c in CandidateFact.__table__.columns}
        assert "original_claim_text" in cols
        assert "claim_text" in cols
        # They must be separate columns
        assert "original_claim_text" != "claim_text"

    def test_default_verification_status(self) -> None:
        fact = CandidateFact()
        assert fact.verification_status == VerificationStatus.NEEDS_CONFIRMATION


class TestJobDescriptionModel:
    def test_tablename(self) -> None:
        assert JobDescription.__tablename__ == "job_descriptions"


class TestJobRequirementModel:
    def test_tablename(self) -> None:
        assert JobRequirement.__tablename__ == "job_requirements"

    def test_default_importance(self) -> None:
        req = JobRequirement()
        assert req.importance == ImportanceLevel.REQUIRED


class TestResumeVersionModel:
    def test_tablename(self) -> None:
        assert ResumeVersion.__tablename__ == "resume_versions"

    def test_unique_constraint_declared(self) -> None:
        """UNIQUE(original_resume_id, version_number) must be in table args."""
        constraint_names = {
            c.name for c in ResumeVersion.__table__.constraints
        }
        assert "uq_resume_versions_resume_version" in constraint_names


class TestProposedEditModel:
    def test_tablename(self) -> None:
        assert ProposedEdit.__tablename__ == "proposed_edits"

    def test_junction_tables_declared(self) -> None:
        assert proposed_edit_facts.name == "proposed_edit_facts"
        assert proposed_edit_requirements.name == "proposed_edit_requirements"

    def test_default_verification_status(self) -> None:
        edit = ProposedEdit()
        assert edit.verification_status == VerificationStatus.NEEDS_CONFIRMATION


class TestExperimentRunModel:
    def test_tablename(self) -> None:
        assert ExperimentRun.__tablename__ == "experiment_runs"

    def test_junction_table_declared(self) -> None:
        assert experiment_run_edits.name == "experiment_run_edits"
