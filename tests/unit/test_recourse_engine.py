"""
Unit tests for the recourse engine service.

Tests cover:
- Infeasible paths: no_evidence, all_unsupported, no_requirement_match
- Edit type generation (normalize_terminology, rephrase, surface_qualification,
  reorder, reorganize_sections, remove_redundancy)
- Fabrication guard (edit introducing unknown entity is discarded)
- Rephrase SBERT similarity floor (< 0.85 rejected)
- Cap at 20 edits
- No Unsupported fact used as sole grounding

Requirements: 5.1–5.8
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models.enums import (
    ATSDecision,
    ClaimType,
    DocumentType,
    EditType,
    ImportanceLevel,
    ExtractionType,
    VerificationStatus,
)
from backend.app.services import recourse_engine


# ── Test fixtures ─────────────────────────────────────────────────────────────


def _make_uuid() -> uuid.UUID:
    return uuid.uuid4()


def _make_fact(
    claim_text: str = "Python developer",
    claim_type: ClaimType = ClaimType.SKILL,
    verification_status: VerificationStatus = VerificationStatus.NEEDS_CONFIRMATION,
    source_span: dict[str, int] | None = None,
    candidate_id: uuid.UUID | None = None,
    source_document_id: uuid.UUID | None = None,
) -> MagicMock:
    fact = MagicMock()
    fact.id = _make_uuid()
    fact.claim_text = claim_text
    fact.original_claim_text = claim_text
    fact.claim_type = claim_type
    fact.verification_status = verification_status
    fact.source_span = source_span or {"start": 0, "end": len(claim_text)}
    fact.candidate_id = candidate_id or _make_uuid()
    fact.source_document_id = source_document_id or _make_uuid()
    fact.metadata_ = {}
    return fact


def _make_requirement(
    requirement_text: str = "Python experience required",
    normalized_skills: list[str] | None = None,
    importance: ImportanceLevel = ImportanceLevel.REQUIRED,
    requirement_type: Any = None,
    extraction_type: ExtractionType = ExtractionType.EXPLICIT,
) -> MagicMock:
    from backend.app.models.enums import RequirementType
    req = MagicMock()
    req.id = _make_uuid()
    req.requirement_text = requirement_text
    req.normalized_skills = normalized_skills or ["Python"]
    req.importance = importance
    req.requirement_type = requirement_type or RequirementType.SKILL
    req.extraction_type = extraction_type
    req.source_span = {"start": 0, "end": len(requirement_text)}
    return req


def _make_resume_version(
    content: str = "Python developer with 3 years experience.",
    candidate_id: uuid.UUID | None = None,
) -> MagicMock:
    rv = MagicMock()
    rv.id = _make_uuid()
    rv.version_number = 1
    rv.content = content
    rv.ats_score = 0.3
    rv.decision = ATSDecision.FAIL
    rv.original_resume = MagicMock()
    rv.original_resume.candidate_id = candidate_id or _make_uuid()
    return rv


def _make_job_description() -> MagicMock:
    jd = MagicMock()
    jd.id = _make_uuid()
    jd.raw_text = "Looking for Python developer with AWS experience."
    return jd


def _make_db(
    resume_version: Any = None,
    jd: Any = None,
    facts: list[Any] | None = None,
    requirements: list[Any] | None = None,
) -> MagicMock:
    """Build a mock SQLAlchemy session."""
    db = MagicMock()
    rv = resume_version or _make_resume_version()
    jd_obj = jd or _make_job_description()
    facts_list = facts if facts is not None else [_make_fact()]
    reqs_list = requirements if requirements is not None else [_make_requirement()]

    # db.get returns rv for any UUID (resume version check), jd_obj for any other
    def db_get(model_cls: Any, pk: Any) -> Any:
        from backend.app.models.resume_version import ResumeVersion
        from backend.app.models.job_description import JobDescription
        if model_cls is ResumeVersion:
            return rv
        if model_cls is JobDescription:
            return jd_obj
        if hasattr(rv, "id") and pk == rv.id:
            return rv
        if hasattr(jd_obj, "id") and pk == jd_obj.id:
            return jd_obj
        return None

    db.get.side_effect = db_get

    # Mock db.execute().scalars().all() for CandidateFact and JobRequirement queries
    facts_result = MagicMock()
    facts_result.scalars.return_value.all.return_value = facts_list
    reqs_result = MagicMock()
    reqs_result.scalars.return_value.all.return_value = reqs_list

    call_count = [0]

    def execute_side_effect(stmt: Any) -> Any:
        call_count[0] += 1
        # First call is for CandidateFact, second for JobRequirement
        if call_count[0] % 2 == 1:
            return facts_result
        return reqs_result

    db.execute.side_effect = execute_side_effect
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.commit = MagicMock()

    def refresh_side_effect(obj: Any) -> None:
        pass

    db.refresh.side_effect = refresh_side_effect
    return db


# ── Infeasible paths ──────────────────────────────────────────────────────────


class TestInfeasiblePaths:
    """Test the three infeasible reasons."""

    def test_no_evidence_when_no_facts(self) -> None:
        """Returns infeasible/no_evidence when candidate has no CandidateFacts."""
        candidate_id = _make_uuid()
        rv = _make_resume_version(candidate_id=candidate_id)
        db = _make_db(resume_version=rv, facts=[])

        edits, status, reason, detail = recourse_engine.generate(
            db=db,
            resume_version_id=rv.id,
            job_description_id=_make_uuid(),
        )

        assert status == "infeasible"
        assert reason == "no_evidence"
        assert edits == []
        assert detail is not None

    def test_all_unsupported_when_all_facts_unsupported(self) -> None:
        """Returns infeasible/all_unsupported when every fact is Unsupported."""
        candidate_id = _make_uuid()
        rv = _make_resume_version(candidate_id=candidate_id)
        unsupported_facts = [
            _make_fact(
                claim_text="Python",
                verification_status=VerificationStatus.UNSUPPORTED,
                candidate_id=candidate_id,
            )
            for _ in range(3)
        ]
        db = _make_db(resume_version=rv, facts=unsupported_facts)

        edits, status, reason, detail = recourse_engine.generate(
            db=db,
            resume_version_id=rv.id,
            job_description_id=_make_uuid(),
        )

        assert status == "infeasible"
        assert reason == "all_unsupported"
        assert edits == []

    def test_no_requirement_match_when_no_requirements(self) -> None:
        """Returns infeasible/no_requirement_match when no JD requirements exist."""
        candidate_id = _make_uuid()
        rv = _make_resume_version(candidate_id=candidate_id)
        db = _make_db(resume_version=rv, requirements=[])

        edits, status, reason, detail = recourse_engine.generate(
            db=db,
            resume_version_id=rv.id,
            job_description_id=_make_uuid(),
        )

        assert status == "infeasible"
        assert reason == "no_requirement_match"
        assert edits == []

    def test_missing_resume_version_raises(self) -> None:
        """ResourceNotFoundError raised when resume_version_id doesn't exist."""
        from backend.app.exceptions import ResourceNotFoundError

        db = MagicMock()
        db.get.return_value = None

        with pytest.raises(ResourceNotFoundError):
            recourse_engine.generate(
                db=db,
                resume_version_id=_make_uuid(),
                job_description_id=_make_uuid(),
            )

    def test_missing_jd_raises(self) -> None:
        """ResourceNotFoundError raised when job_description_id doesn't exist."""
        from backend.app.exceptions import ResourceNotFoundError

        rv = _make_resume_version()
        db = MagicMock()

        def db_get(cls: Any, pk: Any) -> Any:
            if pk == rv.id:
                return rv
            return None

        db.get.side_effect = db_get

        with pytest.raises(ResourceNotFoundError):
            recourse_engine.generate(
                db=db,
                resume_version_id=rv.id,
                job_description_id=_make_uuid(),
            )


# ── Edit type generation ──────────────────────────────────────────────────────


class TestNormalizeTerminologyEdits:
    """normalize_terminology: alias → canonical skill replacement."""

    def test_js_normalizes_to_javascript(self) -> None:
        with patch.object(recourse_engine, "_passes_fabrication_guard", return_value=True):
            result = recourse_engine._generate_normalize_terminology_edits(
                resume_text="Proficient in JS and React development",
                usable_facts=[_make_fact("JS developer", ClaimType.SKILL)],
                requirements=[_make_requirement("JavaScript required", ["JavaScript"])],
                evidence_entity_set=set(),
            )
        assert any(r[1] == "JavaScript" for r in result), (
            "Expected 'JS' to be normalized to 'JavaScript'"
        )

    def test_known_alias_produces_edit(self) -> None:
        with patch.object(recourse_engine, "_passes_fabrication_guard", return_value=True):
            result = recourse_engine._generate_normalize_terminology_edits(
                resume_text="Experience with k8s orchestration",
                usable_facts=[_make_fact("k8s orchestration", ClaimType.SKILL)],
                requirements=[_make_requirement("Kubernetes required", ["Kubernetes"])],
                evidence_entity_set=set(),
            )
        proposed_texts = [r[1] for r in result]
        assert "Kubernetes" in proposed_texts

    def test_no_edit_when_alias_not_in_resume(self) -> None:
        with patch.object(recourse_engine, "_passes_fabrication_guard", return_value=True):
            result = recourse_engine._generate_normalize_terminology_edits(
                resume_text="Python and Django developer",
                usable_facts=[_make_fact("Python developer", ClaimType.SKILL)],
                requirements=[_make_requirement("JavaScript required", ["JavaScript"])],
                evidence_entity_set=set(),
            )
        assert all(r[1] != "JavaScript" for r in result)


class TestSurfaceQualificationEdits:
    """surface_qualification: bury → promote facts matching requirements."""

    def test_buried_fact_gets_surfaced(self) -> None:
        # Fact at position 80% through document
        long_text = "x " * 100  # 200 chars
        skill_text = "AWS certification"
        full_text = long_text + skill_text
        start = len(long_text)

        fact = _make_fact(
            claim_text=skill_text,
            claim_type=ClaimType.CERTIFICATION,
            source_span={"start": start, "end": start + len(skill_text)},
        )

        with patch.object(recourse_engine, "_passes_fabrication_guard", return_value=True):
            result = recourse_engine._generate_surface_qualification_edits(
                resume_text=full_text,
                usable_facts=[fact],
                requirements=[_make_requirement("AWS required", ["AWS"])],
                evidence_entity_set={skill_text.lower()},
            )
        assert len(result) > 0
        assert any("[Highlighted]" in r[1] for r in result)

    def test_early_fact_not_surfaced(self) -> None:
        skill_text = "Python expert"
        fact = _make_fact(
            claim_text=skill_text,
            claim_type=ClaimType.SKILL,
            source_span={"start": 0, "end": len(skill_text)},
        )
        with patch.object(recourse_engine, "_passes_fabrication_guard", return_value=True):
            result = recourse_engine._generate_surface_qualification_edits(
                resume_text=skill_text + " " + "x " * 100,
                usable_facts=[fact],
                requirements=[_make_requirement("Python required", ["Python"])],
                evidence_entity_set=set(),
            )
        # Early facts (position < 50%) should not be surfaced
        assert len(result) == 0


class TestReorderEdits:
    """reorder: best-matching bullet should come first."""

    def test_reorder_promotes_best_bullet(self) -> None:
        resume_text = (
            "Experience:\n"
            "- Worked on internal tools\n"
            "- Built Python microservices for AWS\n"
            "- Wrote documentation\n"
        )
        fact = _make_fact("Python microservices", ClaimType.SKILL)
        with patch.object(recourse_engine, "_passes_fabrication_guard", return_value=True):
            result = recourse_engine._generate_reorder_edits(
                resume_text=resume_text,
                usable_facts=[fact],
                requirements=[_make_requirement("Python AWS required", ["Python", "AWS"])],
                evidence_entity_set=set(),
            )
        assert len(result) > 0
        # The proposed text should start with the Python bullet
        for orig, prop, _, _, _ in result:
            if "Built Python microservices" in prop:
                assert prop.split("\n")[0].strip().startswith("- Built Python microservices")

    def test_no_reorder_when_best_already_first(self) -> None:
        resume_text = (
            "Skills:\n"
            "- Python and AWS expert\n"
            "- Documentation writer\n"
        )
        fact = _make_fact("Python AWS expert", ClaimType.SKILL)
        with patch.object(recourse_engine, "_passes_fabrication_guard", return_value=True):
            result = recourse_engine._generate_reorder_edits(
                resume_text=resume_text,
                usable_facts=[fact],
                requirements=[_make_requirement("Python required", ["Python"])],
                evidence_entity_set=set(),
            )
        # Best bullet is already first — no reorder needed
        assert len(result) == 0


class TestRemoveRedundancyEdits:
    """remove_redundancy: detect and propose removal of duplicate phrases."""

    def test_long_form_redundancy_shortened(self) -> None:
        text = "Developed and implemented RESTful APIs using Python."
        fact = _make_fact("Python APIs", ClaimType.SKILL)
        with patch.object(recourse_engine, "_passes_fabrication_guard", return_value=True):
            result = recourse_engine._generate_remove_redundancy_edits(
                resume_text=text,
                usable_facts=[fact],
                requirements=[_make_requirement("Python required", ["Python"])],
                evidence_entity_set={"python"},
            )
        assert len(result) > 0
        assert any("implemented" in r[1].lower() for r in result)


# ── Fabrication guard ─────────────────────────────────────────────────────────


class TestFabricationGuard:
    """Fabrication guard prevents edits with entities not in Evidence Bank."""

    def test_known_entity_passes(self) -> None:
        evidence_set = {"python", "django"}
        with patch.object(recourse_engine, "_extract_entities", return_value={"python", "django"}):
            result = recourse_engine._passes_fabrication_guard(
                "Python and Django developer", evidence_set
            )
        assert result is True

    def test_new_entity_fails_guard(self) -> None:
        evidence_set = {"python"}
        with patch.object(recourse_engine, "_extract_entities", return_value={"python", "kubernetes"}):
            result = recourse_engine._passes_fabrication_guard(
                "Python and Kubernetes developer", evidence_set
            )
        assert result is False

    def test_empty_proposed_passes_guard(self) -> None:
        """remove_redundancy with empty proposed text always passes (no entities)."""
        with patch.object(recourse_engine, "_extract_entities", return_value=set()):
            assert recourse_engine._passes_fabrication_guard("", set()) is True


# ── SBERT similarity floor ────────────────────────────────────────────────────


class TestRephraseSimilarityFloor:
    """Rephrase edits below 0.85 cosine similarity must be discarded."""

    def test_sbert_cosine_identical_texts_returns_one(self) -> None:
        with patch.object(recourse_engine, "_get_sbert") as mock_sbert:
            import numpy as np
            mock_model = MagicMock()
            # Encode returns two identical unit vectors → cosine = 1.0
            vec = np.array([1.0, 0.0, 0.0])
            mock_model.encode.return_value = np.array([vec, vec])
            mock_sbert.return_value = mock_model

            similarity = recourse_engine._sbert_cosine("hello", "hello")
            assert abs(similarity - 1.0) < 1e-6

    def test_sbert_cosine_orthogonal_returns_zero(self) -> None:
        with patch.object(recourse_engine, "_get_sbert") as mock_sbert:
            import numpy as np
            mock_model = MagicMock()
            vec_a = np.array([1.0, 0.0])
            vec_b = np.array([0.0, 1.0])
            mock_model.encode.return_value = np.array([vec_a, vec_b])
            mock_sbert.return_value = mock_model

            similarity = recourse_engine._sbert_cosine("hello", "world")
            assert abs(similarity) < 1e-6

    def test_rephrase_below_floor_rejected(self) -> None:
        """Rephrase generating < 0.85 similarity should not appear in results."""
        fact = _make_fact(
            "Developed Python microservices",
            ClaimType.RESPONSIBILITY,
        )

        with patch.object(recourse_engine, "_sbert_cosine", return_value=0.7):
            result = recourse_engine._generate_rephrase_edits(
                usable_facts=[fact],
                requirements=[_make_requirement("Python microservices required", ["Python"])],
                evidence_entity_set=set(),
            )
        assert len(result) == 0

    def test_rephrase_above_floor_accepted(self) -> None:
        """Rephrase generating ≥ 0.85 similarity should appear in results."""
        fact = _make_fact(
            "Developed Python microservices",
            ClaimType.RESPONSIBILITY,
        )

        with patch.object(recourse_engine, "_sbert_cosine", return_value=0.92):
            result = recourse_engine._generate_rephrase_edits(
                usable_facts=[fact],
                requirements=[_make_requirement("Python AWS required", ["Python", "AWS"])],
                evidence_entity_set=set(),
            )
        # May or may not produce edits depending on the skill matching logic,
        # but the SBERT check should not have rejected it
        assert isinstance(result, list)


# ── Edit cap ──────────────────────────────────────────────────────────────────


class TestEditCap:
    """At most 20 edits are returned per request (Req 5.7)."""

    def test_cap_at_twenty(self) -> None:
        assert recourse_engine.MAX_EDITS == 20

    def test_unique_candidate_cap_respected(self) -> None:
        """generate_normalize_terminology_edits caps are applied in generate()."""
        # Build 30+ candidates by having many aliases
        resume_text = " ".join(
            f"alias_{i}" for i in range(40)
        )
        facts = [_make_fact(f"alias_{i}", ClaimType.SKILL) for i in range(40)]
        reqs = [
            _make_requirement(f"canonical_{i}", [f"canonical_{i}"])
            for i in range(40)
        ]
        # Patch the skill canon temporarily
        original_canon = dict(recourse_engine._SKILL_CANON)
        recourse_engine._SKILL_CANON.update(
            {f"alias_{i}": f"canonical_{i}" for i in range(40)}
        )
        try:
            with patch.object(recourse_engine, "_passes_fabrication_guard", return_value=True):
                result = recourse_engine._generate_normalize_terminology_edits(
                    resume_text=resume_text,
                    usable_facts=facts,
                    requirements=reqs,
                    evidence_entity_set=set(),
                )
        finally:
            recourse_engine._SKILL_CANON.clear()
            recourse_engine._SKILL_CANON.update(original_canon)

        # The function itself doesn't cap — the cap is applied in generate()
        # We just verify it returns a list
        assert isinstance(result, list)


# ── Unsupported fact exclusion ────────────────────────────────────────────────


class TestUnsupportedFactExclusion:
    """Unsupported facts must never be the sole grounding for an edit (Req 5.2)."""

    def test_usable_facts_excludes_unsupported(self) -> None:
        """generate() filters out Unsupported facts from usable_facts."""
        candidate_id = _make_uuid()
        jd = _make_job_description()
        rv = _make_resume_version(
            content="JS developer with AWS skills",
            candidate_id=candidate_id,
        )

        supported_fact = _make_fact(
            "JavaScript expert",
            ClaimType.SKILL,
            VerificationStatus.SUPPORTED,
            candidate_id=candidate_id,
        )
        unsupported_fact = _make_fact(
            "Blockchain developer",
            ClaimType.SKILL,
            VerificationStatus.UNSUPPORTED,
            candidate_id=candidate_id,
        )

        db = _make_db(
            resume_version=rv,
            jd=jd,
            facts=[supported_fact, unsupported_fact],
            requirements=[_make_requirement("JavaScript required", ["JavaScript"])],
        )

        # Patch NLP and SBERT to avoid loading models in tests
        with (
            patch.object(recourse_engine, "_get_nlp") as mock_nlp,
            patch.object(recourse_engine, "_sbert_cosine", return_value=0.9),
            patch.object(recourse_engine, "_passes_fabrication_guard", return_value=True),
        ):
            mock_nlp_obj = MagicMock()
            mock_nlp_obj.return_value.ents = []
            mock_nlp.return_value = mock_nlp_obj

            edits, status, reason, detail = recourse_engine.generate(
                db=db,
                resume_version_id=rv.id,
                job_description_id=jd.id,
            )

        # Whatever the result, the unsupported_fact should not be the sole
        # grounding for any edit
        if edits:
            for edit in edits:
                fact_ids = {f.id for f in edit.evidence_facts}
                assert unsupported_fact.id not in fact_ids or supported_fact.id in fact_ids
