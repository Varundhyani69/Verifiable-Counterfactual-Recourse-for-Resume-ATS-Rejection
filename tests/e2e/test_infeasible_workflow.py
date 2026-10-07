"""
E2E tests — infeasible recourse workflow.

When all candidate facts are Unsupported, the recourse engine must return
an infeasible result with constraints_violated and partial_result fields.

Owner: Shahin
Requirements: 5.7, 5.8, 6.5, 6.6
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.main import app


# ── Fixtures ──────────────────────────────────────────────────────────────────


@contextmanager
def _override_db(mock_db: MagicMock) -> Generator[None, None, None]:
    """Override the get_db FastAPI dependency with a mock session."""
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


def _make_mock_db() -> MagicMock:
    db = MagicMock()
    db.get.return_value = None
    db.flush.return_value = None
    db.refresh.return_value = None
    db.commit.return_value = None
    db.add.return_value = None
    db.close.return_value = None
    return db


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_infeasible_all_unsupported_returns_correct_reason() -> None:
    """
    When all facts are Unsupported, generate returns infeasible with reason='all_unsupported'.

    The response must include:
    - status == "infeasible"
    - reason in the expected set
    - constraints_violated (non-null list)
    - partial_result (non-null object)

    Requirements: 5.7, 5.8
    """
    version_id = uuid.uuid4()
    jd_id = uuid.uuid4()

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.routers.recourse.recourse_engine.generate",
            return_value=([], "infeasible", "all_unsupported", "All facts are Unsupported."),
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/recourse/generate",
                json={
                    "resume_version_id": str(version_id),
                    "job_description_id": str(jd_id),
                },
            )

    assert response.status_code == 201
    data = response.json()["data"]

    # Core infeasibility assertions
    assert data["status"] == "infeasible"
    assert data["reason"] == "all_unsupported"


def test_infeasible_response_has_constraints_violated_field() -> None:
    """
    Infeasible response must include a constraints_violated list (Req 6.5).
    """
    version_id = uuid.uuid4()
    jd_id = uuid.uuid4()

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.routers.recourse.recourse_engine.generate",
            return_value=([], "infeasible", "all_unsupported", "All facts Unsupported."),
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/recourse/generate",
                json={
                    "resume_version_id": str(version_id),
                    "job_description_id": str(jd_id),
                },
            )

    data = response.json()["data"]
    assert "constraints_violated" in data
    assert isinstance(data["constraints_violated"], list)


def test_infeasible_response_has_partial_result_field() -> None:
    """
    Infeasible response must include a partial_result object (Req 6.6).
    """
    version_id = uuid.uuid4()
    jd_id = uuid.uuid4()

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.routers.recourse.recourse_engine.generate",
            return_value=([], "infeasible", "no_evidence", "No usable evidence found."),
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/recourse/generate",
                json={
                    "resume_version_id": str(version_id),
                    "job_description_id": str(jd_id),
                },
            )

    data = response.json()["data"]
    assert "partial_result" in data
    partial = data["partial_result"]
    assert "edits" in partial
    assert "total_edit_cost" in partial
    assert "projected_score" in partial


def test_infeasible_no_requirement_match_reason() -> None:
    """
    When no edit can be matched to a JD requirement, reason is 'no_requirement_match'.

    Requirements: 5.7
    """
    version_id = uuid.uuid4()
    jd_id = uuid.uuid4()

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.routers.recourse.recourse_engine.generate",
            return_value=(
                [],
                "infeasible",
                "no_requirement_match",
                "No edit could be linked to a JobRequirement.",
            ),
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/recourse/generate",
                json={
                    "resume_version_id": str(version_id),
                    "job_description_id": str(jd_id),
                },
            )

    data = response.json()["data"]
    assert data["status"] == "infeasible"
    assert data["reason"] == "no_requirement_match"


def test_infeasible_response_envelope_has_no_error_key() -> None:
    """
    Infeasible response must use the success envelope {data: ...}, not {error: ...}.

    An infeasible result is a valid workflow outcome — not an API error.
    """
    version_id = uuid.uuid4()
    jd_id = uuid.uuid4()

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.routers.recourse.recourse_engine.generate",
            return_value=([], "infeasible", "all_unsupported", "All facts Unsupported."),
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/recourse/generate",
                json={
                    "resume_version_id": str(version_id),
                    "job_description_id": str(jd_id),
                },
            )

    body = response.json()
    assert "data" in body
    assert "error" not in body
