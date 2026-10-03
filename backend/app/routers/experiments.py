"""
API router for experiment logger endpoints.

    POST /api/experiments               — create a new experiment run
    GET  /api/experiments/{id}          — retrieve a single experiment run
    GET  /api/experiments/{id}/report   — full report with all edits
    GET  /api/experiments               — paginated, filtered list

Requirements: 10.1–10.8
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.response import success_response
from backend.app.schemas.experiment import (
    ExperimentRunCreate,
    ExperimentRunResponse,
)
from backend.app.services import experiment_logger

router = APIRouter(tags=["experiments"])


@router.post("/experiments")
async def create_experiment(
    body: ExperimentRunCreate,
    db: Session = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """Create a new append-only experiment run record."""
    run = experiment_logger.create_run(db=db, payload=body)
    response = ExperimentRunResponse.model_validate(run)
    return success_response(response.model_dump(mode="json"), status_code=201)  # type: ignore[return-value]


@router.get("/experiments/{run_id}")
async def get_experiment(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """Retrieve a single experiment run by ID."""
    run = experiment_logger.get_run(db=db, run_id=run_id)
    response = ExperimentRunResponse.model_validate(run)
    return success_response(response.model_dump(mode="json"))  # type: ignore[return-value]


@router.get("/experiments/{run_id}/report")
async def get_experiment_report(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """Full experiment report with all generated ProposedEdits (including rejected)."""
    report = experiment_logger.get_report(db=db, run_id=run_id)
    return success_response(report.model_dump(mode="json"))  # type: ignore[return-value]


@router.get("/experiments")
async def list_experiments(
    baseline_method: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    threshold: float | None = Query(None),
    model_name: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """
    Paginated, AND-filtered list of experiment runs.

    Zero results return an empty list with a message, not an error.
    """
    result = experiment_logger.list_runs(
        db=db,
        baseline_method=baseline_method,
        start_date=start_date,
        end_date=end_date,
        threshold=threshold,
        model_name=model_name,
        page=page,
        page_size=page_size,
    )
    return success_response(result.model_dump(mode="json"))  # type: ignore[return-value]
