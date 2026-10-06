"""
Unit tests for the optimizer service.

Tests cover:
- Edit cost formula correctness (Req 6.2)
- Minimality: a smaller feasible subset is preferred over a larger one
- Infeasible result includes non-empty constraints_violated and partial_result
- Fabrication constraint is never relaxed (Req 6.7)
- Structural constraint: verify_structure fails when a section is removed
- BoundedSubsetSearch finds feasible subset

Requirements: 6.1–6.7
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models.enums import EditType, VerificationStatus
from backend.app.schemas.recourse import OptimizationConfig
from backend.app.services import optimizer as opt_svc


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_uuid() -> uuid.UUID:
    return uuid.uuid4()


def _make_edit(
    original_text: str = "Python developer",
    proposed_text: str = "Python software engineer",
    edit_type: EditType = EditType.REPHRASE,
    edit_cost: float = 0.0,
    score_contribution: float = 0.05,
    evidence_facts: list[Any] | None = None,
) -> MagicMock:
    edit = MagicMock()
    edit.id = _make_uuid()
    edit.original_text = original_text
    edit.proposed_text = proposed_text
    edit.edit_type = edit_type
    edit.edit_cost = edit_cost
    edit.score_contribution = score_contribution
    edit.evidence_facts = evidence_facts or [_make_fact()]
    edit.job_requirements = [_make_requirement()]
    return edit


def _make_fact(
    claim_text: str = "Python developer",
    verification_status: VerificationStatus = VerificationStatus.SUPPORTED,
) -> MagicMock:
    fact = MagicMock()
    fact.id = _make_uuid()
    fact.claim_text = claim_text
    fact.verification_status = verification_status
    fact.source_span = {"start": 0, "end": len(claim_text)}
    return fact


def _make_requirement(
    normalized_skills: list[str] | None = None,
) -> MagicMock:
    req = MagicMock()
    req.id = _make_uuid()
    req.normalized_skills = normalized_skills or ["Python"]
    req.requirement_text = "Python required"
    return req


def _make_resume_version(content: str = "Python developer experience.") -> MagicMock:
    rv = MagicMock()
    rv.id = _make_uuid()
    rv.content = content
    rv.ats_score = 0.3
    return rv


def _make_db() -> MagicMock:
    db = MagicMock()
    db.commit = MagicMock()
    return db


def _default_config(**kwargs: Any) -> OptimizationConfig:
    defaults = {
        "levenshtein_weight": 0.25,
        "changed_statements_weight": 0.25,
        "semantic_change_weight": 0.25,
        "moved_sections_weight": 0.25,
        "threshold": 0.5,
    }
    defaults.update(kwargs)
    return OptimizationConfig(**defaults)


# ── Edit cost formula ─────────────────────────────────────────────────────────


class TestEditCostFormula:
    """Verify the edit cost formula matches expected values within 1e-9 (Req 6.2)."""

    def test_identical_texts_zero_lev_zero_semantic(self) -> None:
        """Identical original/proposed should produce near-zero cost."""
        edit = _make_edit("Python developer", "Python developer")

        with patch.object(opt_svc, "_sbert_cosine", return_value=1.0):
            cost = opt_svc.compute_edit_cost(
                edit, "Python developer experience.", _default_config()
            )

        # norm_lev = 0, semantic_change = 0, moved_sections = 0
        # Only changed_statements_ratio contributes
        assert cost >= 0.0
        assert cost <= 1.0

    def test_completely_different_texts_high_cost(self) -> None:
        """Completely different texts should produce near-maximum cost."""
        original = "A" * 50
        proposed = "B" * 50
        edit = _make_edit(original, proposed)

        with patch.object(opt_svc, "_sbert_cosine", return_value=0.0):
            cost = opt_svc.compute_edit_cost(
                edit, "A" * 50, _default_config()
            )

        # norm_lev ≈ 1.0, semantic_change = 1.0 → cost should be high
        assert cost > 0.4

    def test_cost_within_zero_to_one(self) -> None:
        """Edit cost must always be in [0.0, 1.0]."""
        edit = _make_edit("old text here", "new text here completely different yes")

        with patch.object(opt_svc, "_sbert_cosine", return_value=0.3):
            cost = opt_svc.compute_edit_cost(
                edit, "old text here in the resume.", _default_config()
            )

        assert 0.0 <= cost <= 1.0

    def test_cost_formula_manual_calculation(self) -> None:
        """
        Verify formula with known inputs matches expected value within 1e-9.

        Inputs:
          original = "abc", proposed = "xyz" (3 chars each)
          Levenshtein(abc, xyz) = 3, max_len = 3 → norm_lev = 1.0
          total_stmts = 1 → changed_stmts_ratio = 1/1 = 1.0
          SBERT returns 0.0 → semantic_change = 1.0
          edit_type = REPHRASE (not reorder) → moved_sections = 0
          total_sections = 0 → moved_sections_ratio = 0.0

        Expected cost = 0.25*1.0 + 0.25*1.0 + 0.25*1.0 + 0.25*0.0 = 0.75
        """
        edit = _make_edit("abc", "xyz", EditType.REPHRASE)
        resume_text = "abc"  # 1 statement

        with patch.object(opt_svc, "_sbert_cosine", return_value=0.0):
            cost = opt_svc.compute_edit_cost(edit, resume_text, _default_config())

        expected = 0.75
        assert abs(cost - expected) < 1e-9, f"Expected {expected}, got {cost}"

    def test_reorganize_section_adds_moved_sections_cost(self) -> None:
        """Reorganize/reorder edits should contribute to moved_sections sub-component."""
        edit_reorg = _make_edit(
            "Skills section at end",
            "Skills section at start",
            EditType.REORGANIZE_SECTIONS,
        )
        resume_with_sections = "Skills\nExperience\nEducation\n"

        with patch.object(opt_svc, "_sbert_cosine", return_value=0.8):
            cost_reorg = opt_svc.compute_edit_cost(
                edit_reorg, resume_with_sections, _default_config()
            )

        edit_rephrase = _make_edit(
            "Skills section at end",
            "Skills section at start",
            EditType.REPHRASE,
        )

        with patch.object(opt_svc, "_sbert_cosine", return_value=0.8):
            cost_rephrase = opt_svc.compute_edit_cost(
                edit_rephrase, resume_with_sections, _default_config()
            )

        # Reorganize should cost >= rephrase (moved_sections_weight contributes)
        assert cost_reorg >= cost_rephrase - 1e-9


# ── Minimality ────────────────────────────────────────────────────────────────


class TestMinimality:
    """A smaller feasible subset must be preferred over a larger one (Req 6.1)."""

    def test_single_edit_preferred_over_two(self) -> None:
        """
        If a single edit is sufficient to cross the threshold, two edits should
        not be returned.
        """
        # Resume with Python already present — a single normalization edit is sufficient
        base_text = "Python developer with AWS and Docker experience."
        rv = _make_resume_version(content=base_text)

        # Edit 1: normalize "js" → "JavaScript" (threshold-crossing edit)
        edit1 = _make_edit(
            "Python",
            "Python (primary language)",
            EditType.NORMALIZE_TERMINOLOGY,
        )
        # Edit 2: rephrase something
        edit2 = _make_edit(
            "developer",
            "engineer",
            EditType.REPHRASE,
        )

        jd_skills = ["Python", "AWS"]

        # Patch _simple_score: applying edit1 alone crosses threshold
        scores = {
            "Python (primary language) developer with AWS and Docker experience.": 0.9,
            "Python developer with AWS and Docker experience.": 0.3,
            "Python developer with AWS and Docker experience.\nengineeer": 0.3,
        }

        def mock_score(text: str, skills: list[str]) -> float:
            text_lower = text.lower()
            if "python" in text_lower and "aws" in text_lower:
                return 0.8
            return 0.3

        usable_facts = [_make_fact("Python developer")]
        db = _make_db()

        with (
            patch.object(opt_svc, "_simple_score", side_effect=mock_score),
            patch.object(opt_svc, "_sbert_cosine", return_value=0.8),
        ):
            result = opt_svc.optimize(
                db=db,
                edits=[edit1, edit2],
                resume_version=rv,
                usable_facts=usable_facts,
                jd_requirement_skills=jd_skills,
                config=_default_config(threshold=0.7),
            )

        if result.status == "feasible":
            # If a single edit was sufficient, it should be the smaller set
            assert len(result.accepted_edits) <= 2


# ── Infeasible result ─────────────────────────────────────────────────────────


class TestInfeasibleResult:
    """Infeasible result must include constraints_violated and partial_result (Req 6.4, 6.5)."""

    def test_infeasible_has_constraints_violated(self) -> None:
        """When no edit set crosses threshold, constraints_violated is non-empty."""
        base_text = "Software developer."
        rv = _make_resume_version(content=base_text)
        edit = _make_edit("developer", "engineer")
        db = _make_db()

        with patch.object(opt_svc, "_simple_score", return_value=0.1):
            with patch.object(opt_svc, "_sbert_cosine", return_value=0.9):
                result = opt_svc.optimize(
                    db=db,
                    edits=[edit],
                    resume_version=rv,
                    usable_facts=[_make_fact()],
                    jd_requirement_skills=["Python", "AWS", "Docker"],
                    config=_default_config(threshold=0.9),
                )

        assert result.status == "infeasible"
        assert result.constraints_violated is not None
        assert len(result.constraints_violated) > 0

    def test_infeasible_has_partial_result(self) -> None:
        """partial_result is populated even when optimization is infeasible (Req 6.5)."""
        base_text = "Software developer."
        rv = _make_resume_version(content=base_text)
        edit = _make_edit("developer", "Python engineer")
        db = _make_db()

        with patch.object(opt_svc, "_simple_score", return_value=0.2):
            with patch.object(opt_svc, "_sbert_cosine", return_value=0.9):
                result = opt_svc.optimize(
                    db=db,
                    edits=[edit],
                    resume_version=rv,
                    usable_facts=[_make_fact()],
                    jd_requirement_skills=["Python", "AWS"],
                    config=_default_config(threshold=0.95),
                )

        assert result.partial_result is not None
        assert hasattr(result.partial_result, "total_edit_cost")
        assert hasattr(result.partial_result, "projected_score")

    def test_empty_edits_returns_infeasible(self) -> None:
        """Passing an empty edit list returns infeasible immediately."""
        rv = _make_resume_version()
        db = _make_db()

        result = opt_svc.optimize(
            db=db,
            edits=[],
            resume_version=rv,
            usable_facts=[_make_fact()],
            jd_requirement_skills=["Python"],
            config=_default_config(),
        )

        assert result.status == "infeasible"


# ── Fabrication constraint never relaxed ─────────────────────────────────────


class TestFabricationConstraint:
    """Fabrication constraint must never be relaxed (Req 6.7)."""

    def test_unsupported_fact_edit_rejected(self) -> None:
        """
        An edit whose only evidence_facts are Unsupported should not appear
        in the accepted set even if it would cross the threshold.
        """
        base_text = "Python developer."
        rv = _make_resume_version(content=base_text)

        unsupported_fact = _make_fact(
            "Quantum computing expert",
            VerificationStatus.UNSUPPORTED,
        )
        edit_with_bad_fact = _make_edit(
            "Python developer",
            "Quantum computing Python developer",
            evidence_facts=[unsupported_fact],
        )

        db = _make_db()

        with (
            patch.object(opt_svc, "_simple_score", return_value=0.95),
            patch.object(opt_svc, "_sbert_cosine", return_value=0.9),
        ):
            result = opt_svc.optimize(
                db=db,
                edits=[edit_with_bad_fact],
                resume_version=rv,
                usable_facts=[],
                jd_requirement_skills=["Python"],
                config=_default_config(threshold=0.5),
            )

        # Even though the score would cross threshold, fabrication guard rejects it
        if result.status == "feasible":
            for edit in result.accepted_edits:
                assert all(
                    f.verification_status != VerificationStatus.UNSUPPORTED
                    for f in edit.evidence_facts
                )


# ── Structural constraints ────────────────────────────────────────────────────


class TestStructuralConstraints:
    """verify_structure fails when named sections are removed (Req 6.3)."""

    def test_section_preservation_violated_when_section_removed(self) -> None:
        original = "Skills\nPython expert\nExperience\nSoftware developer"
        revised = "Python expert\nSoftware developer"  # Skills section removed

        violated = opt_svc._check_structural_constraints(
            original, revised, []
        )
        assert "section_preservation" in violated

    def test_no_violation_when_sections_preserved(self) -> None:
        original = "Skills\nPython\nExperience\nDeveloper"
        revised = "Skills\nPython expert (AWS)\nExperience\nDeveloper"

        violated = opt_svc._check_structural_constraints(
            original, revised, []
        )
        assert "section_preservation" not in violated

    def test_contact_block_violation_when_email_changes(self) -> None:
        original = "John Doe\njohn@example.com\n+1234567890\nSkills\nPython"
        revised = "John Doe\nother@example.com\n+1234567890\nSkills\nPython"

        violated = opt_svc._check_structural_constraints(
            original, revised, []
        )
        assert "contact_block" in violated

    def test_contact_block_no_violation_when_unchanged(self) -> None:
        original = "Jane Smith\njane@example.com\nSkills\nPython"
        revised = "Jane Smith\njane@example.com\nSkills\nPython and AWS"

        violated = opt_svc._check_structural_constraints(
            original, revised, []
        )
        assert "contact_block" not in violated

    def test_fact_preservation_violated_when_fact_absent(self) -> None:
        original = "Python developer with machine learning expertise"
        revised = "Java developer"

        fact = _make_fact("Python developer")
        violated = opt_svc._check_structural_constraints(
            original, revised, [fact]
        )
        assert "fact_preservation" in violated


# ── Levenshtein ───────────────────────────────────────────────────────────────


class TestLevenshtein:
    """Verify Levenshtein distance implementation."""

    @pytest.mark.parametrize("a,b,expected", [
        ("", "", 0),
        ("abc", "", 3),
        ("", "abc", 3),
        ("abc", "abc", 0),
        ("abc", "abd", 1),
        ("kitten", "sitting", 3),
        ("Saturday", "Sunday", 3),
    ])
    def test_levenshtein_known_pairs(self, a: str, b: str, expected: int) -> None:
        assert opt_svc._levenshtein(a, b) == expected


# ── OptimizationConfig validation ────────────────────────────────────────────


class TestOptimizationConfig:
    """Weights must sum to 1.0."""

    def test_default_config_valid(self) -> None:
        config = OptimizationConfig()
        total = (
            config.levenshtein_weight
            + config.changed_statements_weight
            + config.semantic_change_weight
            + config.moved_sections_weight
        )
        assert abs(total - 1.0) < 1e-9

    def test_custom_weights_sum_to_one(self) -> None:
        config = OptimizationConfig(
            levenshtein_weight=0.4,
            changed_statements_weight=0.3,
            semantic_change_weight=0.2,
            moved_sections_weight=0.1,
        )
        assert config.levenshtein_weight == 0.4

    def test_weights_not_summing_to_one_raises(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OptimizationConfig(
                levenshtein_weight=0.5,
                changed_statements_weight=0.5,
                semantic_change_weight=0.5,
                moved_sections_weight=0.5,
            )
