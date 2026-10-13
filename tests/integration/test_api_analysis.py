"""Integration tests for ATS analysis endpoint (Task 17 — Yash)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.main import app
from backend.app.routers import analysis as analysis_router
from backend.app.services import evidence_extractor
from backend.app.services.ats_scorer import DISCLOSURE
from tests.yash_support import make_session, mock_score_result, seed_job_description, seed_resume


@pytest.fixture
def api(monkeypatch):
    with make_session() as db:
        monkeypatch.setattr(
            analysis_router,
            "ats_score",
            lambda resume_text, jd_text, config: mock_score_result(),
        )
        monkeypatch.setattr(evidence_extractor, "extract", lambda db, resume: None)
        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                yield client, db
        finally:
            app.dependency_overrides.pop(get_db, None)


def test_analysis_full_lifecycle(api):
    client, db = api
    resume = seed_resume(db)
    jd = seed_job_description(db)
    db.commit()

    resp = client.post(
        "/api/analysis",
        json={
            "resume_id": str(resume.id),
            "job_description_id": str(jd.id),
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["version_number"] == 1
    assert data["decision"] in ("pass", "fail")
    assert isinstance(data["disclosure"], str)
    assert len(data["disclosure"]) > 0
    assert isinstance(data["score_breakdown"]["total_score"], float)


def test_analysis_invalid_resume_id(api):
    client, db = api
    jd = seed_job_description(db)
    db.commit()

    resp = client.post(
        "/api/analysis",
        json={
            "resume_id": str(uuid.uuid4()),
            "job_description_id": str(jd.id),
        },
    )
    assert resp.status_code == 404


def test_analysis_invalid_jd_id(api):
    client, db = api
    resume = seed_resume(db)
    db.commit()

    resp = client.post(
        "/api/analysis",
        json={
            "resume_id": str(resume.id),
            "job_description_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 404


def test_analysis_disclosure_string_present(api):
    client, db = api
    resume = seed_resume(db)
    jd = seed_job_description(db)
    db.commit()

    resp = client.post(
        "/api/analysis",
        json={
            "resume_id": str(resume.id),
            "job_description_id": str(jd.id),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["disclosure"] == DISCLOSURE


def test_analysis_creates_version_number_1(api):
    client, db = api
    resume = seed_resume(db)
    jd = seed_job_description(db)
    db.commit()

    resp = client.post(
        "/api/analysis",
        json={
            "resume_id": str(resume.id),
            "job_description_id": str(jd.id),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["version_number"] == 1
