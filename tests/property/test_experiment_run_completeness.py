"""
Property test — ExperimentRun field completeness and rate bounds (Property 23, Task 22.2).

Feature: verifiable-counterfactual-recourse, Property 23:
    For any created ExperimentRun, all 13 required fields must be present.
    The three values inside grounding_metrics (evidence_grounding_rate,
    unsupported_claim_rate, original_fact_preservation_rate) must each be in [0.0, 1.0].

Validates: Requirements 10.1, 10.5
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.schemas.experiment import ExperimentRunCreate, GroundingMetrics
from backend.app.services import experiment_logger

# Strategy for generating valid rates in [0.0, 1.0]
_rate_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Strategy for baseline methods
_baseline_strategy = st.sampled_from(["original_resume", "generic_llm", "proposed"])


def _make_db_mock():
    db = MagicMock()

    def _refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()

    db.refresh.side_effect = _refresh
    return db


@given(
    eg_rate=_rate_strategy,
    uc_rate=_rate_strategy,
    fp_rate=_rate_strategy,
    baseline_method=_baseline_strategy,
    orig_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    final_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    decision_flipped=st.booleans(),
    edit_cost=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    random_seed=st.one_of(st.none(), st.integers(min_value=0, max_value=2**31 - 1)),
)
@settings(max_examples=50, deadline=None)
def test_experiment_run_completeness_and_rate_bounds(
    eg_rate: float,
    uc_rate: float,
    fp_rate: float,
    baseline_method: str,
    orig_score: float,
    final_score: float,
    threshold: float,
    decision_flipped: bool,
    edit_cost: float,
    random_seed: int | None,
):
    """
    All 13 fields present on created ExperimentRun, and grounding_metrics rates in [0.0, 1.0].
    """
    db = _make_db_mock()

    payload = ExperimentRunCreate(
        resume_id=uuid.uuid4(),
        job_description_id=uuid.uuid4(),
        model_configuration={"sbert_model": "all-MiniLM-L6-v2", "threshold": threshold},
        baseline_method=baseline_method,
        original_score=orig_score,
        final_score=final_score,
        threshold=threshold,
        decision_flipped=decision_flipped,
        total_edit_cost=edit_cost,
        grounding_metrics=GroundingMetrics(
            evidence_grounding_rate=eg_rate,
            unsupported_claim_rate=uc_rate,
            original_fact_preservation_rate=fp_rate,
        ),
        random_seed=random_seed,
        edit_ids=[],
    )

    run = experiment_logger.create_run(db=db, payload=payload)

    # 13 required fields:
    # 1. id
    assert hasattr(run, "id") and run.id is not None
    # 2. created_at
    assert hasattr(run, "created_at") and run.created_at is not None
    # 3. resume_id
    assert hasattr(run, "resume_id") and run.resume_id == payload.resume_id
    # 4. job_description_id
    assert hasattr(run, "job_description_id")
    assert run.job_description_id == payload.job_description_id
    # 5. model_configuration
    assert hasattr(run, "model_configuration") and run.model_configuration is not None
    # 6. baseline_method
    assert hasattr(run, "baseline_method") and run.baseline_method == baseline_method
    # 7. original_score
    assert hasattr(run, "original_score") and run.original_score == orig_score
    # 8. final_score
    assert hasattr(run, "final_score") and run.final_score == final_score
    # 9. threshold
    assert hasattr(run, "threshold") and run.threshold == threshold
    # 10. decision_flipped
    assert hasattr(run, "decision_flipped") and run.decision_flipped == decision_flipped
    # 11. total_edit_cost
    assert hasattr(run, "total_edit_cost") and run.total_edit_cost == edit_cost
    # 12. grounding_metrics
    assert hasattr(run, "grounding_metrics") and run.grounding_metrics is not None
    gm = run.grounding_metrics
    assert 0.0 <= gm["evidence_grounding_rate"] <= 1.0
    assert 0.0 <= gm["unsupported_claim_rate"] <= 1.0
    assert 0.0 <= gm["original_fact_preservation_rate"] <= 1.0
    # 13. random_seed
    assert hasattr(run, "random_seed")
    if random_seed is not None:
        assert run.random_seed == random_seed
