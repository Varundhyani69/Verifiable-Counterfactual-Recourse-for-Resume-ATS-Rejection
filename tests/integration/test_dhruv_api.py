"""Exercise Tasks 7 and 8 through HTTP with persisted records."""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.main import app
from backend.app.services import jd_analyzer
from tests.dhruv_support import make_nlp, make_session, seed_evidence


@pytest.fixture
def api(monkeypatch):
    with make_session() as db:
        monkeypatch.setattr(jd_analyzer, "_get_nlp", lambda: make_nlp())
        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                yield client, db
        finally:
            app.dependency_overrides.pop(get_db, None)


def test_jd_create_and_get(api):
    client, _ = api
    text = "Must have JS and Python. Docker preferred."
    created = client.post("/api/job-descriptions", json={"text": text})
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["raw_text"] == text
    assert data["warning"] is None
    assert data["requirements"][0]["normalized_skills"] == ["JavaScript", "Python"]
    fetched = client.get(f"/api/job-descriptions/{data['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["requirements"] == data["requirements"]
    assert "warning" not in fetched.json()["data"]


def test_jd_zero_requirements_warning(api):
    client, _ = api
    response = client.post("/api/job-descriptions", json={"text": "Welcome to our company."})
    assert response.status_code == 201
    payload = response.json()
    assert payload["warning"] == payload["data"]["warning"]
    assert payload["data"]["requirements"] == []
    assert client.get(f"/api/job-descriptions/{payload['data']['id']}").status_code == 200


@pytest.mark.parametrize(
    "body",
    [{}, {"text": ""}, {"text": " \n\t"}, {"text": "x" * 10_001}, {"text": None}, {"text": 123}],
)
def test_jd_invalid_body_returns_error_envelope(api, body):
    response = api[0].post("/api/job-descriptions", json=body)
    assert response.status_code == 422
    assert set(response.json()) == {"error"}
    assert set(response.json()["error"]) == {"code", "message"}


def test_evidence_review_and_patch_round_trip(api):
    client, db = api
    candidate, facts = seed_evidence(db)
    url = f"/api/candidates/{candidate}/evidence"
    response = client.get(url)
    assert response.status_code == 200
    original = response.json()["data"]["facts"][0]
    assert original["metadata"]["skills"] == ["Python"]
    changed = client.patch(
        f"{url}/{facts[0].id}",
        json={
            "claim_text": "Built Python APIs.",
            "verification_status": "Supported",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["original_claim_text"] == original["original_claim_text"]
    assert changed.json()["data"]["claim_text"] == "Built Python APIs."
    retrieved = client.get(url).json()["data"]["facts"][0]
    assert retrieved == changed.json()["data"]


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"claim_text": ""},
        {"claim_text": " "},
        {"claim_text": "x" * 2001},
        {"verification_status": "invalid"},
        {"original_claim_text": "overwrite"},
        {"claim_text": None},
        {"verification_status": None},
        {"claim_text": "valid", "verification_status": "invalid"},
    ],
)
def test_invalid_patch_changes_nothing(api, patch):
    client, db = api
    candidate, facts = seed_evidence(db)
    url = f"/api/candidates/{candidate}/evidence"
    before = client.get(url).json()
    response = client.patch(f"{url}/{facts[0].id}", json=patch)
    assert response.status_code == 422
    assert "error" in response.json()
    assert client.get(url).json() == before


def test_missing_resources_and_candidate_scope(api):
    client, db = api
    candidate, facts = seed_evidence(db)
    for url in (
        f"/api/job-descriptions/{uuid.uuid4()}",
        f"/api/candidates/{uuid.uuid4()}/evidence",
    ):
        response = client.get(url)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
    for owner, fact_id in ((uuid.uuid4(), facts[0].id), (candidate, uuid.uuid4())):
        response = client.patch(
            f"/api/candidates/{owner}/evidence/{fact_id}",
            json={"verification_status": "Unsupported"},
        )
        assert response.status_code == 404
    assert (
        client.get(f"/api/candidates/{candidate}/evidence").json()["data"]["facts"][0][
            "verification_status"
        ]
        == "Needs Confirmation"
    )


def test_invalid_uuid_returns_422(api):
    assert api[0].get("/api/job-descriptions/not-a-uuid").status_code == 422
    assert api[0].get("/api/candidates/not-a-uuid/evidence").status_code == 422
