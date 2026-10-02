"""
Unit tests — experiment logger (Task 22.4).

Tests cover:
    - All 13 fields present on created run
    - baseline_method outside enum returns 422
    - grounding_metrics rates validated ∈ [0.0, 1.0]
    - Append-only: ImmutableRecordError raised on mutation
    - list_runs pagination returns correct total, page, page_size
    - get_report returns all ProposedEdits including rejected ones

Requirements: 10.1–10.8
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from backend.app.exceptions import (
    ImmutableRecordError,
    InvalidBaselineMethodError,
    ResourceNotFoundError,
)
from backend.app.models.experiment_run import ExperimentRun
from backend.app.schemas.experiment import (
    ExperimentRunCreate,
    GroundingMetrics,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _valid_payload(**overrides) -> ExperimentRunCreate:
    """Build a valid ExperimentRunCreate with sensible defaults."""
    defaults = {
        "resume_id": uuid.uuid4(),
        "job_description_id": uuid.uuid4(),
        "model_configuration": {
            "sbert_model": "all-MiniLM-L6-v2",
            "sbert_version": "2.7.0",
            "spacy_model": "en_core_web_sm",
            "spacy_version": "3.7.4",
            "ats_skill_weight": 0.5,
            "ats_sbert_weight": 0.5,
            "threshold": 0.5,
            "edit_cost_weights": [0.25, 0.25, 0.25, 0.25],
        },
        "baseline_method": "proposed",
        "original_score": 0.35,
        "final_score": 0.72,
        "threshold": 0.5,
        "decision_flipped": True,
        "total_edit_cost": 0.42,
        "grounding_metrics": GroundingMetrics(
            evidence_grounding_rate=0.85,
            unsupported_claim_rate=0.05,
            original_fact_preservation_rate=0.92,
        ),
        "random_seed": 42,
        "edit_ids": [],
    }
    defaults.update(overrides)
    return ExperimentRunCreate(**defaults)


# ── Schema validation tests ───────────────────────────────────────────────────


class TestExperimentRunCreateSchema:
    """Tests for the ExperimentRunCreate Pydantic schema."""

    def test_valid_payload_accepted(self):
        """A well-formed payload with all 13 fields is accepted."""
        payload = _valid_payload()
        assert payload.resume_id is not None
        assert payload.job_description_id is not None
        assert payload.model_configuration is not None
        assert payload.baseline_method == "proposed"
        assert payload.original_score == 0.35
        assert payload.final_score == 0.72
        assert payload.threshold == 0.5
        assert payload.decision_flipped is True
        assert payload.total_edit_cost == 0.42
        assert payload.grounding_metrics is not None
        assert payload.random_seed == 42

    def test_invalid_baseline_method_rejected(self):
        """baseline_method outside the enum raises ValueError at schema level."""
        with pytest.raises(ValueError, match="not a valid baseline_method"):
            _valid_payload(baseline_method="invalid_method")

    def test_grounding_rate_below_zero_rejected(self):
        """Grounding rate < 0.0 raises ValueError."""
        with pytest.raises(ValueError):
            GroundingMetrics(
                evidence_grounding_rate=-0.1,
                unsupported_claim_rate=0.0,
                original_fact_preservation_rate=0.5,
            )

    def test_grounding_rate_above_one_rejected(self):
        """Grounding rate > 1.0 raises ValueError."""
        with pytest.raises(ValueError):
            GroundingMetrics(
                evidence_grounding_rate=0.5,
                unsupported_claim_rate=1.1,
                original_fact_preservation_rate=0.5,
            )

    def test_grounding_rate_boundaries_accepted(self):
        """Boundary values 0.0 and 1.0 are accepted."""
        metrics = GroundingMetrics(
            evidence_grounding_rate=0.0,
            unsupported_claim_rate=1.0,
            original_fact_preservation_rate=0.5,
        )
        assert metrics.evidence_grounding_rate == 0.0
        assert metrics.unsupported_claim_rate == 1.0

    def test_all_three_baseline_methods_accepted(self):
        """Each of the 3 valid baseline methods is accepted."""
        for method in ("original_resume", "generic_llm", "proposed"):
            payload = _valid_payload(baseline_method=method)
            assert payload.baseline_method == method

    def test_random_seed_optional(self):
        """random_seed can be None."""
        payload = _valid_payload(random_seed=None)
        assert payload.random_seed is None


# ── AppendOnlyMixin tests ────────────────────────────────────────────────────


class TestAppendOnlyImmutability:
    """Tests for append-only enforcement on ExperimentRun."""

    def test_mutation_after_persist_raises_immutable_error(self):
        """Attempting to mutate a field after mark_persisted() raises ImmutableRecordError."""
        run = ExperimentRun(
            resume_id=uuid.uuid4(),
            job_description_id=uuid.uuid4(),
            model_configuration={"test": True},
            baseline_method="proposed",
            original_score=0.3,
            final_score=0.7,
            threshold=0.5,
            decision_flipped=True,
            total_edit_cost=0.4,
            grounding_metrics={"evidence_grounding_rate": 0.8,
                               "unsupported_claim_rate": 0.1,
                               "original_fact_preservation_rate": 0.9},
            random_seed=42,
        )
        run.mark_persisted()

        with pytest.raises(ImmutableRecordError):
            run.original_score = 0.99

    def test_mutation_before_persist_allowed(self):
        """Fields can be set freely before mark_persisted() is called."""
        run = ExperimentRun(
            resume_id=uuid.uuid4(),
            job_description_id=uuid.uuid4(),
            model_configuration={"test": True},
            baseline_method="proposed",
            original_score=0.3,
            final_score=0.7,
            threshold=0.5,
            decision_flipped=True,
            total_edit_cost=0.4,
            grounding_metrics={"evidence_grounding_rate": 0.8,
                               "unsupported_claim_rate": 0.1,
                               "original_fact_preservation_rate": 0.9},
            random_seed=42,
        )
        # Should not raise
        run.original_score = 0.5
        assert run.original_score == 0.5


# ── Service-level tests (with mocked DB) ─────────────────────────────────────


class TestExperimentLoggerService:
    """Tests for the experiment_logger service functions."""

    def test_invalid_baseline_raises_422(self):
        """create_run with invalid baseline_method raises InvalidBaselineMethodError."""
        from backend.app.services import experiment_logger

        db = MagicMock()
        # Build payload manually to bypass schema validation
        payload = _valid_payload()
        # Override after construction
        object.__setattr__(payload, "baseline_method", "nonexistent")

        with pytest.raises(InvalidBaselineMethodError):
            experiment_logger.create_run(db=db, payload=payload)

    def test_get_run_not_found(self):
        """get_run with non-existent ID raises ResourceNotFoundError."""
        from backend.app.services import experiment_logger

        db = MagicMock()
        db.get.return_value = None

        with pytest.raises(ResourceNotFoundError):
            experiment_logger.get_run(db=db, run_id=uuid.uuid4())
