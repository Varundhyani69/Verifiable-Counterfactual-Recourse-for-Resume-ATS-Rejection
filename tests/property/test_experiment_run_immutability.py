"""
Property test — ExperimentRun append-only immutability (Property 24, Task 22.3).

Feature: verifiable-counterfactual-recourse, Property 24:
    After creating an ExperimentRun, attempt to update any field via service layer;
    assert ImmutableRecordError is always raised.

Validates: Requirements 10.8
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.exceptions import ImmutableRecordError
from backend.app.schemas.experiment import ExperimentRunCreate, GroundingMetrics
from backend.app.services import experiment_logger

# Strategy for fields to attempt to mutate
_mutable_fields = st.sampled_from([
    ("original_score", 0.99),
    ("final_score", 0.88),
    ("threshold", 0.77),
    ("decision_flipped", True),
    ("total_edit_cost", 5.5),
    ("baseline_method", "generic_llm"),
    ("random_seed", 999),
])


def _make_db_mock():
    db = MagicMock()

    def _refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()

    db.refresh.side_effect = _refresh
    return db


@given(mutation=_mutable_fields)
@settings(max_examples=50, deadline=None)
def test_experiment_run_immutability(mutation: tuple[str, object]):
    """
    Attempting to set any field on a persisted ExperimentRun must raise ImmutableRecordError.
    """
    db = _make_db_mock()

    payload = ExperimentRunCreate(
        resume_id=uuid.uuid4(),
        job_description_id=uuid.uuid4(),
        model_configuration={"threshold": 0.5},
        baseline_method="proposed",
        original_score=0.4,
        final_score=0.7,
        threshold=0.5,
        decision_flipped=True,
        total_edit_cost=1.2,
        grounding_metrics=GroundingMetrics(
            evidence_grounding_rate=1.0,
            unsupported_claim_rate=0.0,
            original_fact_preservation_rate=1.0,
        ),
        random_seed=42,
        edit_ids=[],
    )

    run = experiment_logger.create_run(db=db, payload=payload)

    field_name, new_val = mutation
    with pytest.raises(ImmutableRecordError) as exc_info:
        setattr(run, field_name, new_val)

    assert exc_info.value.code == "IMMUTABLE_RECORD"
    assert "append-only" in exc_info.value.message
