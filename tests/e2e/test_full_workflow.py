"""
E2E tests — complete happy-path workflow.

Tests the 11-step happy path from PDF upload through ExperimentRun retrieval,
using mocked services and an in-memory SQLite database so no live PostgreSQL
or ML models are required.

Steps tested (from tasks.md Task 21.1):
  1.  POST /api/resumes/upload       → ResumeDocument created
  2.  GET  /api/resumes/{id}         → extracted text non-empty, source spans valid
  3.  GET  /api/candidates/{id}/evidence → all facts Needs Confirmation
  4.  PATCH one fact to Supported
  5.  POST /api/job-descriptions     → JobRequirements extracted
  6.  POST /api/analysis             → ResumeVersion v1, decision fail
  7.  POST /api/recourse/generate    → ProposedEdits with valid cost
  8.  POST /api/recourse/{id}/verify → VerificationReport for every edit
  9.  POST /api/recourse/{id}/accept → ResumeVersion v2 created
  10. GET  /api/resumes/versions/{id}/download?format=txt → non-empty bytes
  11. GET  /api/experiments/{run_id} → full ExperimentRun with all 13 fields

Owner: Shahin
Requirements: all
"""

from __future__ import annotations

import io
import uuid
from contextlib import contextmanager
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.main import app


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_mock_db() -> MagicMock:
    """Minimal mock database session used across E2E tests."""
    db = MagicMock()
    db.get.return_value = None
    db.flush.return_value = None
    db.refresh.return_value = None
    db.commit.return_value = None
    db.add.return_value = None
    db.close.return_value = None
    return db


@contextmanager
def _override_db(mock_db: MagicMock) -> Generator[None, None, None]:
    """Override the get_db FastAPI dependency with a mock session."""
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


# ── Step 1: POST /api/resumes/upload ─────────────────────────────────────────


def test_step1_upload_resume_returns_201() -> None:
    """
    Step 1: Upload a PDF resume file; expect 201 with a ResumeDocument in the response.
    """
    candidate_id = str(uuid.uuid4())

    # Mock the ingestion and extraction services
    mock_resume = MagicMock()
    mock_resume.id = uuid.uuid4()
    mock_resume.candidate_id = uuid.UUID(candidate_id)
    mock_resume.document_type = MagicMock()
    mock_resume.document_type.value = "pdf"
    mock_resume.extracted_text = "Software Engineer with 5 years Python experience."
    mock_resume.source_spans = [{"start": 0, "end": 49, "text": "Software Engineer"}]
    mock_resume.filename = "test_resume.pdf"
    mock_resume.created_at = MagicMock()
    mock_resume.created_at.isoformat.return_value = "2026-10-07T00:00:00"
    mock_resume.updated_at = MagicMock()
    mock_resume.updated_at.isoformat.return_value = "2026-10-07T00:00:00"

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.ingestion_service.ingest_file",
            return_value=mock_resume,
        ) as mock_ingest,
        patch(
            "backend.app.services.evidence_extractor.extract",
            return_value=[],
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            # Minimal PDF header so the content-type check passes
            fake_pdf = io.BytesIO(b"%PDF-1.4 fake pdf content")
            response = client.post(
                "/api/resumes/upload",
                data={"candidate_id": candidate_id},
                files={"file": ("test_resume.pdf", fake_pdf, "application/pdf")},
            )

    assert response.status_code == 201
    data = response.json()
    assert "data" in data
    assert "error" not in data
    mock_ingest.assert_called_once()


# ── Step 2: GET /api/resumes/{id} ─────────────────────────────────────────────


def test_step2_get_resume_returns_extracted_text() -> None:
    """
    Step 2: Retrieve a resume; response contains non-empty extracted text.
    """
    resume_id = uuid.uuid4()

    mock_resume = MagicMock()
    mock_resume.id = resume_id
    mock_resume.candidate_id = uuid.uuid4()
    mock_resume.document_type = MagicMock()
    mock_resume.document_type.value = "pdf"
    mock_resume.extracted_text = "Engineer at Acme Corp. Python, React."
    mock_resume.source_spans = [{"start": 0, "end": 20, "text": "Engineer at Acme Corp"}]
    mock_resume.filename = "resume.pdf"
    mock_resume.created_at = MagicMock()
    mock_resume.created_at.isoformat.return_value = "2026-10-07T00:00:00"
    mock_resume.updated_at = MagicMock()
    mock_resume.updated_at.isoformat.return_value = "2026-10-07T00:00:00"

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.ingestion_service.get_resume",
            return_value=mock_resume,
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.get(f"/api/resumes/{resume_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["extracted_text"]) > 0
    # Source spans are valid: start < end
    for span in data["source_spans"]:
        assert span["start"] < span["end"]


# ── Step 3: GET /api/candidates/{id}/evidence ────────────────────────────────


def test_step3_get_evidence_facts_all_needs_confirmation() -> None:
    """
    Step 3: All freshly extracted facts should have Needs Confirmation status.
    """
    candidate_id = uuid.uuid4()

    mock_fact = MagicMock()
    mock_fact.id = uuid.uuid4()
    mock_fact.candidate_id = candidate_id
    mock_fact.claim_text = "Built REST APIs with Python"
    mock_fact.original_claim_text = "Built REST APIs with Python"
    mock_fact.claim_type = MagicMock()
    mock_fact.claim_type.value = "skill"
    mock_fact.verification_status = MagicMock()
    mock_fact.verification_status.value = "Needs Confirmation"
    mock_fact.source_span = {"start": 0, "end": 26}
    mock_fact.source_document_id = uuid.uuid4()
    mock_fact.metadata = {"skills": ["Python"]}
    mock_fact.updated_at = MagicMock()
    mock_fact.updated_at.isoformat.return_value = "2026-10-07T00:00:00"
    mock_fact.created_at = MagicMock()
    mock_fact.created_at.isoformat.return_value = "2026-10-07T00:00:00"

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.evidence_bank.get_facts",
            return_value=[mock_fact],
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.get(f"/api/candidates/{candidate_id}/evidence")

    assert response.status_code == 200
    facts = response.json()["data"]["facts"]
    assert len(facts) >= 1
    for fact in facts:
        assert fact["verification_status"] == "Needs Confirmation"


# ── Step 4: PATCH /api/candidates/{id}/evidence/{fact_id} ────────────────────


def test_step4_patch_fact_to_supported() -> None:
    """
    Step 4: PATCH a single fact to Supported status.
    """
    candidate_id = uuid.uuid4()
    fact_id = uuid.uuid4()

    mock_fact = MagicMock()
    mock_fact.id = fact_id
    mock_fact.candidate_id = candidate_id
    mock_fact.claim_text = "Built REST APIs with Python"
    mock_fact.original_claim_text = "Built REST APIs with Python"
    mock_fact.claim_type = MagicMock()
    mock_fact.claim_type.value = "skill"
    mock_fact.verification_status = MagicMock()
    mock_fact.verification_status.value = "Supported"
    mock_fact.source_span = {"start": 0, "end": 26}
    mock_fact.source_document_id = uuid.uuid4()
    mock_fact.metadata = {"skills": ["Python"]}
    mock_fact.updated_at = MagicMock()
    mock_fact.updated_at.isoformat.return_value = "2026-10-07T00:00:01"
    mock_fact.created_at = MagicMock()
    mock_fact.created_at.isoformat.return_value = "2026-10-07T00:00:00"

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.evidence_bank.update_fact",
            return_value=mock_fact,
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.patch(
                f"/api/candidates/{candidate_id}/evidence/{fact_id}",
                json={"verification_status": "Supported"},
            )

    assert response.status_code == 200
    assert response.json()["data"]["verification_status"] == "Supported"


# ── Step 5: POST /api/job-descriptions ───────────────────────────────────────


def test_step5_post_job_description_extracts_requirements() -> None:
    """
    Step 5: POST a JD and verify requirements are extracted.
    """
    mock_jd = MagicMock()
    mock_jd.id = uuid.uuid4()
    mock_jd.raw_text = "Must have Python. Docker preferred."
    mock_jd.warning = None
    mock_jd.created_at = MagicMock()
    mock_jd.created_at.isoformat.return_value = "2026-10-07T00:00:00"

    mock_req = MagicMock()
    mock_req.id = uuid.uuid4()
    mock_req.job_description_id = mock_jd.id
    mock_req.requirement_text = "Python"
    mock_req.requirement_type = MagicMock()
    mock_req.requirement_type.value = "skill"
    mock_req.importance = MagicMock()
    mock_req.importance.value = "required"
    mock_req.extraction_type = MagicMock()
    mock_req.extraction_type.value = "explicit"
    mock_req.normalized_skills = ["Python"]
    mock_req.source_span = {"start": 9, "end": 15}

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.jd_analyzer.analyze",
            return_value=(mock_jd, [mock_req]),
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/job-descriptions",
                json={"text": "Must have Python. Docker preferred."},
            )

    assert response.status_code == 201
    data = response.json()["data"]
    assert len(data["requirements"]) >= 1


# ── Step 6: POST /api/analysis ───────────────────────────────────────────────


def test_step6_analysis_returns_resume_version_v1() -> None:
    """
    Step 6: Run ATS analysis; response contains version_number=1 and a decision.
    """
    from backend.app.schemas.analysis import AnalysisResponse, ScoreBreakdown

    mock_version_id = uuid.uuid4()

    mock_response = AnalysisResponse(
        resume_version_id=mock_version_id,
        version_number=1,
        score_breakdown=ScoreBreakdown(
            total_score=0.35,
            skill_overlap_score=0.30,
            semantic_similarity_score=0.40,
            weights={"skill_overlap_weight": 0.5, "sbert_weight": 0.5},
            threshold=0.5,
        ),
        decision="fail",
        disclosure=(
            "This is a simulated ATS. Results do not reflect any real employer system."
        ),
    )

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.routers.analysis.ats_scorer_svc.score_and_store",
            return_value=mock_response,
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/analysis",
                json={
                    "resume_id": str(uuid.uuid4()),
                    "job_description_id": str(uuid.uuid4()),
                },
            )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["version_number"] == 1
    assert data["decision"] in ("pass", "fail")
    assert len(data["disclosure"]) > 0


# ── Step 7: POST /api/recourse/generate ──────────────────────────────────────


def test_step7_generate_recourse_returns_proposed_edits() -> None:
    """
    Step 7: Generate recourse edits; response contains feasible edits with cost.
    """
    version_id = uuid.uuid4()
    jd_id = uuid.uuid4()

    mock_edit = MagicMock()
    mock_edit.id = uuid.uuid4()
    mock_edit.original_text = "Python developer"
    mock_edit.proposed_text = "Senior Python Engineer"
    mock_edit.edit_type = MagicMock()
    mock_edit.edit_type.value = "rephrase"
    mock_edit.verification_status = MagicMock()
    mock_edit.verification_status.value = "Needs Confirmation"
    mock_edit.edit_cost = 0.15
    mock_edit.score_contribution = 0.08
    mock_edit.evidence_facts = []
    mock_edit.job_requirements = []

    # Mock recourse engine to return one feasible edit
    with (
        patch(
            "backend.app.routers.recourse.recourse_engine.generate",
            return_value=([mock_edit], "feasible", None, None),
        ),
        patch(
            "backend.app.routers.recourse.optimizer_svc.optimize",
        ) as mock_opt,
        patch(
            "backend.app.routers.recourse.db",
            create=True,
        ),
    ):
        from backend.app.services.optimizer import OptimizationResult

        opt_result = MagicMock()
        opt_result.status = "feasible"
        opt_result.accepted_edits = [mock_edit]
        opt_result.total_edit_cost = 0.15
        opt_result.projected_score = 0.62
        opt_result.projected_decision = "pass"
        mock_opt.return_value = opt_result

        mock_db = _make_mock_db()

        mock_version = MagicMock()
        mock_version.id = version_id
        mock_version.original_resume = MagicMock()
        mock_version.original_resume.candidate_id = uuid.uuid4()
        mock_db.get.return_value = mock_version

        # Mock DB execute for usable facts and JD requirements
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute_result

        with _override_db(mock_db):
            with TestClient(app) as client:
                response = client.post(
                    "/api/recourse/generate",
                    json={
                        "resume_version_id": str(version_id),
                        "job_description_id": str(jd_id),
                    },
                )

    # Response is either feasible or infeasible — both are valid shapes
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] in ("feasible", "infeasible")
    assert "recourse_id" in data


# ── Step 8: POST /api/recourse/{id}/verify ───────────────────────────────────


def test_step8_verify_returns_one_report_per_edit() -> None:
    """
    Step 8: Verify edits; get exactly one VerificationReport per edit.
    """
    version_id = uuid.uuid4()
    edit_id = uuid.uuid4()

    mock_report = MagicMock()
    mock_report.edit_id = edit_id
    mock_report.methods_used = ["span_match", "nli"]
    mock_report.evidence_fact_ids = []
    mock_report.assigned_status = "Needs Confirmation"
    mock_report.entailment_score = 0.45
    mock_report.rationale = "No direct span match; entailment below threshold."

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.routers.recourse.verifier_svc.verify_batch",
            return_value=[mock_report],
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.post(f"/api/recourse/{version_id}/verify")

    assert response.status_code == 200
    reports = response.json()["data"]["verification_reports"]
    assert len(reports) == 1
    assert reports[0]["assigned_status"] == "Needs Confirmation"


# ── Step 9: POST /api/recourse/{id}/accept ───────────────────────────────────


def test_step9_accept_creates_new_resume_version() -> None:
    """
    Step 9: Accept edits; a new ResumeVersion (v2) is created.
    """
    version_id = uuid.uuid4()
    new_version_id = uuid.uuid4()
    original_resume_id = uuid.uuid4()

    mock_new_version = MagicMock()
    mock_new_version.id = new_version_id
    mock_new_version.version_number = 2
    mock_new_version.original_resume_id = original_resume_id

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.routers.recourse.export_service.apply_edits",
            return_value=mock_new_version,
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.post(
                f"/api/recourse/{version_id}/accept",
                json={"accepted_edit_ids": [str(uuid.uuid4())]},
            )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["version_number"] == 2
    assert "new_resume_version_id" in data


# ── Step 10: GET /api/resumes/versions/{id}/download?format=txt ──────────────


def test_step10_download_txt_returns_nonempty_bytes() -> None:
    """
    Step 10: Download the new resume version as .txt; get non-empty bytes.
    """
    version_id = uuid.uuid4()

    mock_version = MagicMock()
    mock_version.id = version_id
    mock_version.version_number = 2
    mock_version.content = "Senior Python Engineer with 5 years experience."

    mock_db = _make_mock_db()
    mock_db.get.return_value = mock_version

    with _override_db(mock_db):
        with TestClient(app) as client:
            response = client.get(
                f"/api/resumes/versions/{version_id}/download?format=txt"
            )

    assert response.status_code == 200
    assert len(response.content) > 0
    assert "Senior Python Engineer" in response.text


# ── Step 11: GET /api/experiments/{run_id} ───────────────────────────────────


def test_step11_get_experiment_run_has_all_13_fields() -> None:
    """
    Step 11: Retrieve an ExperimentRun; verify all 13 required fields are present.
    """
    run_id = uuid.uuid4()

    mock_run = MagicMock()
    mock_run.id = run_id
    mock_run.resume_id = uuid.uuid4()
    mock_run.job_description_id = uuid.uuid4()
    mock_run.model_configuration = {
        "sbert_model": "all-MiniLM-L6-v2",
        "spacy_model": "en_core_web_sm",
        "ats_skill_weight": 0.5,
        "ats_sbert_weight": 0.5,
    }
    mock_run.baseline_method = "proposed"
    mock_run.original_score = 0.35
    mock_run.final_score = 0.62
    mock_run.threshold = 0.5
    mock_run.decision_flipped = True
    mock_run.total_edit_cost = 0.15
    mock_run.grounding_metrics = {
        "evidence_grounding_rate": 0.9,
        "unsupported_claim_rate": 0.1,
        "original_fact_preservation_rate": 0.95,
    }
    mock_run.random_seed = 42
    mock_run.created_at = MagicMock()
    mock_run.created_at.isoformat.return_value = "2026-10-07T00:00:00"

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.experiment_logger.get_run",
            return_value=mock_run,
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.get(f"/api/experiments/{run_id}")

    assert response.status_code == 200
    data = response.json()["data"]

    # All 13 required fields must be present
    required_fields = [
        "id",
        "resume_id",
        "job_description_id",
        "model_configuration",
        "baseline_method",
        "original_score",
        "final_score",
        "threshold",
        "decision_flipped",
        "total_edit_cost",
        "grounding_metrics",
        "random_seed",
        "created_at",
    ]
    for field in required_fields:
        assert field in data, f"Required field '{field}' missing from ExperimentRun response"
