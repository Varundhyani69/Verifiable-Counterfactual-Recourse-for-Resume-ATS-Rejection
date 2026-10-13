"""Integration tests for recourse generation, verification, and edit-status endpoints.
(Task 17 — Yash)
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.exceptions import ResourceNotFoundError
from backend.app.main import app
from backend.app.models.enums import EditType, VerificationStatus
from backend.app.models.proposed_edit import ProposedEdit
from backend.app.routers import recourse as recourse_router
from backend.app.services import explanation_service as explanation_svc
from backend.app.services import recourse_engine, verifier as verifier_svc
from tests.yash_support import (
    make_session,
    mock_score_result,
    seed_job_description,
    seed_resume,
    seed_resume_version,
)


@pytest.fixture
def api(monkeypatch):
    with make_session() as db:
        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                yield client, db
        finally:
            app.dependency_overrides.pop(get_db, None)


def test_recourse_infeasible_path(api, monkeypatch):
    client, db = api
    resume = seed_resume(db)
    jd = seed_job_description(db)
    rv = seed_resume_version(db, resume)
    db.commit()

    # Make recourse engine return infeasible
    monkeypatch.setattr(
        recourse_engine,
        "generate",
        lambda db, resume_version_id, job_description_id: (
            [],
            "infeasible",
            "threshold",
            "No facts.",
        ),
    )

    resp = client.post(
        "/api/recourse/generate",
        json={
            "resume_version_id": str(rv.id),
            "job_description_id": str(jd.id),
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["status"] == "infeasible"
    assert data["partial_result"] is not None
    assert data["partial_result"]["edits"] == []


def test_verify_recourse(api, monkeypatch):
    client, db = api
    resume = seed_resume(db)
    rv = seed_resume_version(db, resume)
    db.commit()

    monkeypatch.setattr(
        verifier_svc,
        "verify_batch",
        lambda db, resume_version_id, llm_config: [],
    )

    resp = client.post(f"/api/recourse/{rv.id}/verify")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["verification_reports"] == []


def test_verify_recourse_not_found(api, monkeypatch):
    client, _ = api
    bad_id = uuid.uuid4()

    monkeypatch.setattr(
        verifier_svc,
        "verify_batch",
        lambda db, resume_version_id, llm_config: (_ for _ in ()).throw(
            ResourceNotFoundError("ResumeVersion", str(resume_version_id))
        ),
    )

    resp = client.post(f"/api/recourse/{bad_id}/verify")
    assert resp.status_code == 404


def test_patch_edit_status_confirm(api, monkeypatch):
    client, db = api
    resume = seed_resume(db)
    rv = seed_resume_version(db, resume)
    edit_id = uuid.uuid4()

    # Build a stub ProposedEdit with Needs Confirmation
    stub_edit = ProposedEdit(
        id=edit_id,
        resume_version_id=rv.id,
        original_text="old",
        proposed_text="new",
        edit_type=EditType.REPHRASE,
        verification_status=VerificationStatus.NEEDS_CONFIRMATION,
        edit_cost=0.1,
        score_contribution=0.05,
    )
    db.add(stub_edit)
    db.commit()

    resp = client.patch(
        f"/api/recourse/edits/{edit_id}/status",
        json={"action": "confirm"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["verification_status"] == "Supported"
    assert data["action_applied"] == "confirm"


def test_patch_edit_status_reject(api):
    client, db = api
    resume = seed_resume(db)
    rv = seed_resume_version(db, resume)
    edit_id = uuid.uuid4()

    stub_edit = ProposedEdit(
        id=edit_id,
        resume_version_id=rv.id,
        original_text="old",
        proposed_text="new",
        edit_type=EditType.REPHRASE,
        verification_status=VerificationStatus.NEEDS_CONFIRMATION,
        edit_cost=0.1,
        score_contribution=0.05,
    )
    db.add(stub_edit)
    db.commit()

    resp = client.patch(
        f"/api/recourse/edits/{edit_id}/status",
        json={"action": "reject"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["action_applied"] == "reject"


def test_patch_edit_invalid_action(api):
    client, _ = api
    resp = client.patch(
        f"/api/recourse/edits/{uuid.uuid4()}/status",
        json={"action": "destroy"},
    )
    assert resp.status_code == 422
