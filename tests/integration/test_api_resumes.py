"""Integration tests for resume ingestion endpoints (Task 17 — Yash)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.exceptions import UnsupportedFileTypeError
from backend.app.main import app
from backend.app.models.enums import DocumentType
from backend.app.models.resume_document import ResumeDocument
from backend.app.services import evidence_extractor, ingestion_service
from tests.yash_support import make_session, seed_resume


def _make_stub_resume(db, text: str, candidate_id: uuid.UUID) -> ResumeDocument:
    """Helper: insert a minimal ResumeDocument and return it."""
    resume = ResumeDocument(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        document_type=DocumentType.MANUAL,
        filename=None,
        extracted_text=text,
        source_spans=[],
    )
    db.add(resume)
    db.flush()
    return resume


@pytest.fixture
def api(monkeypatch):
    with make_session() as db:
        # Bypass evidence extraction (avoids spaCy load)
        monkeypatch.setattr(evidence_extractor, "extract", lambda db, resume: None)

        # Bypass real ingestion (avoids PDF/DOCX/OCR deps)
        def _fake_ingest_manual(*, db, text, candidate_id):
            return _make_stub_resume(db, text, candidate_id)

        def _fake_ingest_file(*, db, file_data, filename, content_type, candidate_id):
            return _make_stub_resume(db, "Uploaded resume", candidate_id)

        monkeypatch.setattr(ingestion_service, "ingest_manual", _fake_ingest_manual)
        monkeypatch.setattr(ingestion_service, "ingest_file", _fake_ingest_file)

        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                yield client, db
        finally:
            app.dependency_overrides.pop(get_db, None)


def test_manual_resume_round_trip(api):
    client, _ = api
    candidate_id = str(uuid.uuid4())
    resp = client.post(
        "/api/resumes/manual",
        json={"text": "Python developer", "candidate_id": candidate_id},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["document_type"] == "manual"
    assert data["extracted_text"] == "Python developer"
    resume_id = data["id"]

    get_resp = client.get(f"/api/resumes/{resume_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["extracted_text"] == "Python developer"


def test_manual_resume_empty_text(api):
    client, _ = api
    resp = client.post(
        "/api/resumes/manual",
        json={"text": "", "candidate_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_manual_resume_missing_candidate_id(api):
    client, _ = api
    resp = client.post("/api/resumes/manual", json={"text": "Hello world"})
    assert resp.status_code == 422


def test_get_resume_not_found(api):
    client, _ = api
    resp = client.get(f"/api/resumes/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_upload_unsupported_type(api, monkeypatch):
    client, _ = api

    def _raise_unsupported(**kwargs):
        raise UnsupportedFileTypeError()

    monkeypatch.setattr(ingestion_service, "ingest_file", _raise_unsupported)
    resp = client.post(
        "/api/resumes/upload",
        files={"file": ("resume.txt", b"fake content", "text/plain")},
        data={"candidate_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 415
