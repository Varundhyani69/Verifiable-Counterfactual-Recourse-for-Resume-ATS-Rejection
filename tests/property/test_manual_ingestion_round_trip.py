"""
Property test — manual ingestion round trip (Property 3, Task 5.4).

Feature: verifiable-counterfactual-recourse, Property 3:
    For any non-empty string of up to 50,000 characters submitted to
    POST /api/resumes/manual, a subsequent GET /api/resumes/{id} must return
    the same text in extracted_text and document_type must equal "manual".

Validates: Requirements 1.10, 1.12
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.database import get_db
from backend.app.main import app
from backend.app.models.resume_document import ResumeDocument

# Skip the entire module when spaCy is not installed — the ingestion
# service calls evidence_extractor which requires spaCy at runtime.
try:
    import spacy  # noqa: F401
    spacy.load("en_core_web_sm")
    _SPACY_AVAILABLE = True
except (ImportError, OSError):
    _SPACY_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _SPACY_AVAILABLE,
    reason="spaCy model 'en_core_web_sm' not installed",
)

# Generate arbitrary non-empty strings up to 1,000 chars
_manual_text_strategy = st.text(min_size=1, max_size=1000, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z", "S"),
))


class _InMemoryStore:
    def __init__(self):
        self.docs: dict[uuid.UUID, ResumeDocument] = {}

    def make_db_mock(self):
        db = MagicMock()

        def _add(obj):
            if isinstance(obj, ResumeDocument):
                if not hasattr(obj, "id") or obj.id is None:
                    obj.id = uuid.uuid4()
                self.docs[obj.id] = obj

        def _refresh(obj):
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = uuid.uuid4()

        def _get(model, obj_id):
            if isinstance(obj_id, str):
                obj_id = uuid.UUID(obj_id)
            return self.docs.get(obj_id)

        db.add.side_effect = _add
        db.refresh.side_effect = _refresh
        db.get.side_effect = _get
        return db


@given(text=_manual_text_strategy)
@settings(max_examples=25, deadline=None)
def test_manual_ingestion_round_trip(text: str):
    """
    POST /api/resumes/manual with text; GET /api/resumes/{id} returns
    identical extracted_text and document_type == 'manual'.
    """
    store = _InMemoryStore()
    mock_db = store.make_db_mock()

    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app, raise_server_exceptions=True)

    try:
        candidate_id = str(uuid.uuid4())
        post_resp = client.post(
            "/api/resumes/manual",
            json={"candidate_id": candidate_id, "text": text},
        )
        assert post_resp.status_code == 201
        data = post_resp.json()["data"]
        doc_id = data["id"]
        assert data["document_type"] == "manual"
        assert data["extracted_text"] == text

        # Subsequent GET /api/resumes/{id}
        get_resp = client.get(f"/api/resumes/{doc_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()["data"]
        assert get_data["id"] == doc_id
        assert get_data["document_type"] == "manual"
        assert get_data["extracted_text"] == text
    finally:
        app.dependency_overrides.clear()
