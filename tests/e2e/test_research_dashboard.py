"""
E2E tests — research evaluation dashboard.

Tests:
  - Create 3 runs with different baseline_method values
  - GET /api/experiments?baseline_method=proposed → only proposed runs returned
  - All 6 summary fields present per item
  - AND-filter semantics (multiple filters → all must match)
  - Zero-results returns message, not error

Owner: Shahin
Requirements: 11.1–11.6
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.main import app
from backend.app.schemas.experiment import ExperimentRunSummary, PaginatedResult


# ── Fixtures ──────────────────────────────────────────────────────────────────


@contextmanager
def _override_db(mock_db: MagicMock) -> Generator[None, None, None]:
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


def _make_summary(
    baseline_method: str = "proposed",
    original_score: float = 0.35,
    final_score: float = 0.65,
    decision_flipped: bool = True,
) -> ExperimentRunSummary:
    return ExperimentRunSummary(
        id=uuid.uuid4(),
        baseline_method=baseline_method,
        original_score=original_score,
        final_score=final_score,
        decision_flipped=decision_flipped,
        created_at=datetime(2026, 10, 7, 12, 0, 0),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_list_experiments_filter_by_baseline_method_returns_only_matching() -> None:
    """
    GET /api/experiments?baseline_method=proposed must return only proposed runs.

    Requirements: 11.2 (AND filter semantics)
    """
    proposed_run = _make_summary("proposed")
    paginated = PaginatedResult(
        items=[proposed_run],
        total=1,
        page=1,
        page_size=20,
    )

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.experiment_logger.list_runs",
            return_value=paginated,
        ) as mock_list,
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.get("/api/experiments?baseline_method=proposed")

    assert response.status_code == 200
    data = response.json()["data"]
    items = data["items"]
    assert len(items) == 1
    assert items[0]["baseline_method"] == "proposed"

    # Verify the filter was passed to the service
    mock_list.assert_called_once()
    call_kwargs = mock_list.call_args.kwargs
    assert call_kwargs.get("baseline_method") == "proposed"


def test_list_experiments_all_6_summary_fields_present() -> None:
    """
    Every item in the paginated list must contain all 6 required summary fields.

    Requirements: 11.6
    """
    runs = [
        _make_summary("original_resume", decision_flipped=False),
        _make_summary("generic_llm", decision_flipped=False),
        _make_summary("proposed", decision_flipped=True),
    ]
    paginated = PaginatedResult(
        items=runs,
        total=3,
        page=1,
        page_size=20,
    )

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.experiment_logger.list_runs",
            return_value=paginated,
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.get("/api/experiments")

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 3

    required_fields = [
        "id",
        "baseline_method",
        "original_score",
        "final_score",
        "decision_flipped",
        "created_at",
    ]
    for item in items:
        for field in required_fields:
            assert field in item, (
                f"Summary field '{field}' missing from experiment list item"
            )


def test_list_experiments_zero_results_returns_empty_items_not_error() -> None:
    """
    Zero-results must return an empty list with a data envelope, NOT an error.

    Requirements: 11.3
    """
    paginated = PaginatedResult(
        items=[],
        total=0,
        page=1,
        page_size=20,
    )

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.experiment_logger.list_runs",
            return_value=paginated,
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.get(
                "/api/experiments?baseline_method=nonexistent_method_xyz"
            )

    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "error" not in body
    assert body["data"]["items"] == []
    assert body["data"]["total"] == 0


def test_list_experiments_and_filter_semantics_multiple_params() -> None:
    """
    Multiple query filters use AND semantics — all filters must match per item.

    This test verifies both filters are forwarded to the service layer.

    Requirements: 11.2
    """
    paginated = PaginatedResult(
        items=[_make_summary("proposed")],
        total=1,
        page=1,
        page_size=20,
    )

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.experiment_logger.list_runs",
            return_value=paginated,
        ) as mock_list,
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.get(
                "/api/experiments?baseline_method=proposed&threshold=0.5"
            )

    assert response.status_code == 200
    call_kwargs = mock_list.call_args.kwargs
    assert call_kwargs.get("baseline_method") == "proposed"
    assert call_kwargs.get("threshold") == pytest.approx(0.5)


def test_list_experiments_pagination_fields_present() -> None:
    """
    Response must include pagination metadata: total, page, page_size.

    Requirements: 11.4
    """
    paginated = PaginatedResult(
        items=[_make_summary()],
        total=42,
        page=2,
        page_size=20,
    )

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.experiment_logger.list_runs",
            return_value=paginated,
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.get("/api/experiments?page=2&page_size=20")

    data = response.json()["data"]
    assert data["total"] == 42
    assert data["page"] == 2
    assert data["page_size"] == 20


def test_list_experiments_three_baseline_methods_all_returned_without_filter() -> None:
    """
    Without a baseline_method filter, all three method types appear.

    Simulates the research dashboard chart data requirement (Req 11.5).
    """
    runs = [
        _make_summary("original_resume"),
        _make_summary("generic_llm"),
        _make_summary("proposed"),
    ]
    paginated = PaginatedResult(
        items=runs,
        total=3,
        page=1,
        page_size=20,
    )

    mock_db = _make_mock_db()

    with (
        patch(
            "backend.app.services.experiment_logger.list_runs",
            return_value=paginated,
        ),
        _override_db(mock_db),
    ):
        with TestClient(app) as client:
            response = client.get("/api/experiments")

    items = response.json()["data"]["items"]
    methods = {item["baseline_method"] for item in items}
    assert methods == {"original_resume", "generic_llm", "proposed"}
