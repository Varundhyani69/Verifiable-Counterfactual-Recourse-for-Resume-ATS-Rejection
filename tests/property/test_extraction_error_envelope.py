"""
Property test — extraction error envelope consistency (Property 2, Task 5.3).

Feature: verifiable-counterfactual-recourse, Property 2:
    For any failure mode in Ingestion_Service (file size exceeded, unsupported format,
    empty extraction, library exception), the HTTP error response must contain a top-level
    error field with both a machine-readable code string and a human-readable message string,
    and must NOT create a partial ResumeDocument record.

Validates: Requirements 1.6, 1.7, 1.8, 1.9
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

# Unsupported extensions/content types
_unsupported_extensions = st.sampled_from(
    [".txt", ".png", ".jpg", ".exe", ".csv", ".json", ".zip"]
)
_corrupt_bytes_strategy = st.binary(min_size=1, max_size=500)


@pytest.fixture
def mock_db():
    db = MagicMock()
    # No rows added
    db.query.return_value.count.return_value = 0
    return db


def _get_client_with_db(mock_db):
    app.dependency_overrides[get_db] = lambda: mock_db
    client = TestClient(app, raise_server_exceptions=False)
    return client


class TestExtractionErrorEnvelope:
    """Property 2 test suite."""

    @given(ext=_unsupported_extensions)
    @settings(max_examples=20, deadline=None)
    def test_unsupported_format_envelope(self, ext: str):
        """Unsupported format returns 415 with {error: {code, message}} and no DB record."""
        mock_db = MagicMock()
        client = _get_client_with_db(mock_db)
        try:
            cid = str(uuid.uuid4())
            response = client.post(
                "/api/resumes/upload",
                data={"candidate_id": cid},
                files={"file": (f"test{ext}", b"some content", "application/octet-stream")},
            )
            assert response.status_code == 415
            data = response.json()
            assert "error" in data
            assert "data" not in data
            assert data["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
            assert isinstance(data["error"]["message"], str) and len(data["error"]["message"]) > 0
            mock_db.add.assert_not_called()
            mock_db.commit.assert_not_called()
        finally:
            app.dependency_overrides.clear()

    @given(corrupt_bytes=_corrupt_bytes_strategy)
    @settings(max_examples=20, deadline=None)
    def test_corrupt_file_envelope(self, corrupt_bytes: bytes):
        """
        Corrupt PDF/DOCX bytes trigger 422 with EXTRACTION_FAILED / EMPTY_EXTRACTION
        and no DB record.
        """
        mock_db = MagicMock()
        client = _get_client_with_db(mock_db)
        try:
            cid = str(uuid.uuid4())
            response = client.post(
                "/api/resumes/upload",
                data={"candidate_id": cid},
                files={"file": ("corrupt.pdf", corrupt_bytes, "application/pdf")},
            )
            assert response.status_code in (422, 415)
            data = response.json()
            assert "error" in data
            assert "data" not in data
            assert isinstance(data["error"]["code"], str)
            assert isinstance(data["error"]["message"], str) and len(data["error"]["message"]) > 0
            mock_db.add.assert_not_called()
            mock_db.commit.assert_not_called()
        finally:
            app.dependency_overrides.clear()

    def test_oversized_file_envelope(self):
        """Oversized file triggers 413 with FILE_TOO_LARGE and no DB record."""
        mock_db = MagicMock()
        client = _get_client_with_db(mock_db)
        try:
            cid = str(uuid.uuid4())
            # 11 MB payload
            large_content = b"0" * (11 * 1024 * 1024)
            response = client.post(
                "/api/resumes/upload",
                data={"candidate_id": cid},
                files={"file": ("large.pdf", large_content, "application/pdf")},
            )
            assert response.status_code == 413
            data = response.json()
            assert "error" in data
            assert "data" not in data
            assert data["error"]["code"] == "FILE_TOO_LARGE"
            assert isinstance(data["error"]["message"], str) and len(data["error"]["message"]) > 0
            mock_db.add.assert_not_called()
            mock_db.commit.assert_not_called()
        finally:
            app.dependency_overrides.clear()
