"""Integration tests for experiment logger endpoints (Task 17 — Yash)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.main import app
from tests.yash_support import make_session, seed_job_description, seed_resume


@pytest.fixture
def api(monkeypatch):
    with make_session() as db:
        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                yield client, db
        finally:
            app.dependency_overrides.pop(get_db, None)


def _experiment_payload(resume_id: str, jd_id: str) -> dict:
    return {
        "resume_id": resume_id,
        "job_description_id": jd_id,
        "model_configuration": {"sbert_model": "all-MiniLM-L6-v2"},
        "baseline_method": "original_resume",
        "original_score": 0.4,
        "final_score": 0.72,
        "threshold": 0.5,
        "decision_flipped": True,
        "total_edit_cost": 0.3,
        "grounding_metrics": {
            "evidence_grounding_rate": 0.8,
            "unsupported_claim_rate": 0.1,
            "original_fact_preservation_rate": 0.9,
        },
        "random_seed": 42,
        "edit_ids": [],
    }


def test_create_experiment_valid(api):
    client, db = api
    resume = seed_resume(db)
    jd = seed_job_description(db)
    db.commit()

    resp = client.post(
        "/api/experiments",
        json=_experiment_payload(str(resume.id), str(jd.id)),
    )
    assert resp.status_code == 201
    assert "id" in resp.json()["data"]


def test_get_experiment(api):
    client, db = api
    resume = seed_resume(db)
    jd = seed_job_description(db)
    db.commit()

    created = client.post(
        "/api/experiments",
        json=_experiment_payload(str(resume.id), str(jd.id)),
    )
    assert created.status_code == 201
    run_id = created.json()["data"]["id"]

    fetched = client.get(f"/api/experiments/{run_id}")
    assert fetched.status_code == 200
    data = fetched.json()["data"]
    assert data["id"] == run_id
    assert data["baseline_method"] == "original_resume"
    assert data["original_score"] == 0.4


def test_create_experiment_invalid_baseline_method(api):
    client, db = api
    resume = seed_resume(db)
    jd = seed_job_description(db)
    db.commit()

    payload = _experiment_payload(str(resume.id), str(jd.id))
    payload["baseline_method"] = "nonexistent"

    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 422


def test_create_experiment_missing_required_field(api):
    client, db = api
    resume = seed_resume(db)
    jd = seed_job_description(db)
    db.commit()

    payload = _experiment_payload(str(resume.id), str(jd.id))
    del payload["grounding_metrics"]

    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 422


def test_get_experiment_not_found(api):
    client, _ = api
    resp = client.get(f"/api/experiments/{uuid.uuid4()}")
    assert resp.status_code == 404
