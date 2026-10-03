"""
Experiment logger service.

Records, retrieves, and lists experiment runs with append-only enforcement.

Public API:
    create_run(db, payload)              → ExperimentRun
    get_run(db, run_id)                  → ExperimentRun
    list_runs(db, filters, page, size)   → PaginatedResult
    get_report(db, run_id)               → ExperimentReport

Requirements: 10.1–10.8
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.exceptions import (
    InvalidBaselineMethodError,
    ResourceNotFoundError,
)
from backend.app.models.enums import BaselineMethod
from backend.app.models.experiment_run import ExperimentRun
from backend.app.models.proposed_edit import ProposedEdit
from backend.app.schemas.experiment import (
    ExperimentReport,
    ExperimentRunCreate,
    ExperimentRunResponse,
    ExperimentRunSummary,
    PaginatedResult,
    ProposedEditSummary,
)

# ── Allowed baseline methods ─────────────────────────────────────────────────

_ALLOWED_BASELINES: set[str] = {m.value for m in BaselineMethod}


# ── Public API ────────────────────────────────────────────────────────────────


def create_run(*, db: Session, payload: ExperimentRunCreate) -> ExperimentRun:
    """
    Create a new experiment run record.

    Validates all 13 required fields, baseline_method enum membership,
    and grounding_metrics rate bounds. Links all ProposedEdits (including
    rejected) via the ``experiment_run_edits`` junction table.

    After initial flush, marks the record as persisted so AppendOnlyMixin
    will reject any subsequent mutation.

    Args:
        db: Active database session.
        payload: Validated ExperimentRunCreate schema.

    Returns:
        The persisted ExperimentRun.

    Raises:
        InvalidBaselineMethodError: Invalid baseline_method value.
    """
    # ── Validate baseline_method ──────────────────────────────────────────
    if payload.baseline_method not in _ALLOWED_BASELINES:
        raise InvalidBaselineMethodError(payload.baseline_method)

    # ── Build run ─────────────────────────────────────────────────────────
    run = ExperimentRun(
        resume_id=payload.resume_id,
        job_description_id=payload.job_description_id,
        model_configuration=payload.model_configuration,
        baseline_method=payload.baseline_method,
        original_score=payload.original_score,
        final_score=payload.final_score,
        threshold=payload.threshold,
        decision_flipped=payload.decision_flipped,
        total_edit_cost=payload.total_edit_cost,
        grounding_metrics=payload.grounding_metrics.model_dump(),
        random_seed=payload.random_seed,
    )

    db.add(run)
    db.flush()  # Get the ID assigned

    # ── Link edits ────────────────────────────────────────────────────────
    if payload.edit_ids:
        edits = (
            db.execute(
                select(ProposedEdit).where(ProposedEdit.id.in_(payload.edit_ids))
            )
            .scalars()
            .all()
        )
        run.all_edits = list(edits)

    db.commit()
    db.refresh(run)

    # Activate append-only immutability
    run.mark_persisted()

    return run


def get_run(*, db: Session, run_id: uuid.UUID) -> ExperimentRun:
    """
    Retrieve an experiment run by primary key.

    Raises:
        ResourceNotFoundError: No run with the given ID.
    """
    run = db.get(ExperimentRun, run_id)
    if run is None:
        raise ResourceNotFoundError("ExperimentRun", str(run_id))
    return run


def list_runs(
    *,
    db: Session,
    baseline_method: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    threshold: float | None = None,
    model_name: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResult:
    """
    List experiment runs with AND-filter semantics and pagination.

    Zero results return an empty list, not an error.

    Args:
        db: Active database session.
        baseline_method: Filter by baseline method (exact match).
        start_date: Filter by created_at >= start_date.
        end_date: Filter by created_at <= end_date.
        threshold: Filter by threshold (exact match).
        model_name: Filter by model_configuration containing the model name.
        page: 1-based page number.
        page_size: Items per page (default 20).

    Returns:
        PaginatedResult with items, total, page, and page_size.
    """
    stmt = select(ExperimentRun)
    count_stmt = select(func.count(ExperimentRun.id))

    # ── Apply AND filters ─────────────────────────────────────────────────
    if baseline_method is not None:
        stmt = stmt.where(ExperimentRun.baseline_method == baseline_method)
        count_stmt = count_stmt.where(ExperimentRun.baseline_method == baseline_method)

    if start_date is not None:
        stmt = stmt.where(ExperimentRun.created_at >= start_date)
        count_stmt = count_stmt.where(ExperimentRun.created_at >= start_date)

    if end_date is not None:
        stmt = stmt.where(ExperimentRun.created_at <= end_date)
        count_stmt = count_stmt.where(ExperimentRun.created_at <= end_date)

    if threshold is not None:
        stmt = stmt.where(ExperimentRun.threshold == threshold)
        count_stmt = count_stmt.where(ExperimentRun.threshold == threshold)

    if model_name is not None:
        # JSON containment check for model name in model_configuration
        stmt = stmt.where(
            ExperimentRun.model_configuration["sbert_model"].astext == model_name
        )
        count_stmt = count_stmt.where(
            ExperimentRun.model_configuration["sbert_model"].astext == model_name
        )

    # ── Pagination ────────────────────────────────────────────────────────
    total: int = db.execute(count_stmt).scalar_one()
    offset = (page - 1) * page_size
    stmt = stmt.order_by(ExperimentRun.created_at.desc()).offset(offset).limit(page_size)

    rows = db.execute(stmt).scalars().all()
    items = [ExperimentRunSummary.model_validate(r) for r in rows]

    return PaginatedResult(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


def get_report(*, db: Session, run_id: uuid.UUID) -> ExperimentReport:
    """
    Build a full experiment report including ALL ProposedEdits (even rejected).

    Raises:
        ResourceNotFoundError: No run with the given ID.
    """
    run = get_run(db=db, run_id=run_id)

    run_response = ExperimentRunResponse.model_validate(run)
    edit_summaries = [ProposedEditSummary.model_validate(e) for e in run.all_edits]

    return ExperimentReport(run=run_response, all_edits=edit_summaries)
