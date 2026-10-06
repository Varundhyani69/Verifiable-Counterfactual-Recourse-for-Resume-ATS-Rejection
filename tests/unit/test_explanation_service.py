"""
Unit tests for the Explanation Service.

Covers:
- All 7 ExplanationCard fields are present and non-null
- Needs Confirmation card includes can_confirm / can_reject controls
- Aggregate metrics are computed correctly
- Reject does NOT trigger recourse regeneration (no DB side-effects)
- Confirm/Reject status transitions

Requirements: 8.1–8.6
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models.enums import VerificationStatus
from backend.app.services.explanation_service import (
    AggregateMetrics,
    ExplanationCard,
    build_aggregate,
    build_card,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_fact(claim_text: str = "Built Python REST APIs") -> MagicMock:
    fact = MagicMock()
    fact.id = uuid.uuid4()
    fact.claim_text = claim_text
    return fact


def _make_requirement(req_text: str = "5+ years Python experience") -> MagicMock:
    req = MagicMock()
    req.id = uuid.uuid4()
    req.requirement_text = req_text
    return req


def _make_edit(
    status: VerificationStatus = VerificationStatus.NEEDS_CONFIRMATION,
    edit_type: str = "rephrase",
    score_contribution: float = 0.05,
    edit_cost: float = 0.12,
) -> MagicMock:
    edit = MagicMock()
    edit.id = uuid.uuid4()
    edit.original_text = "Worked on Python APIs"
    edit.proposed_text = "Developed Python REST APIs (utilizing FastAPI)"
    edit.edit_type = MagicMock()
    edit.edit_type.value = edit_type
    edit.verification_status = MagicMock()
    edit.verification_status.value = status.value
    edit.score_contribution = score_contribution
    edit.edit_cost = edit_cost
    return edit


# ── ExplanationCard field completeness ───────────────────────────────────────


def test_build_card_all_7_required_fields_non_null() -> None:
    """All 7 required ExplanationCard fields must be non-null (Property 20)."""
    fact = _make_fact()
    req = _make_requirement()
    edit = _make_edit()

    card = build_card(edit, [fact], [req])

    # Field 1
    assert card.prose_description is not None and len(card.prose_description) > 0
    # Field 2
    assert card.ats_improvement_reason is not None and len(card.ats_improvement_reason) > 0
    # Fields 3 & 4
    assert len(card.evidence_fact_ids) == 1
    assert len(card.evidence_claim_texts) == 1
    # Fields 5 & 6
    assert len(card.job_requirement_ids) == 1
    assert len(card.requirement_texts) == 1
    # Field 7
    assert card.score_contribution is not None


def test_build_card_ids_match_inputs() -> None:
    fact = _make_fact("Built microservices")
    req = _make_requirement("Python microservices required")
    edit = _make_edit()

    card = build_card(edit, [fact], [req])
    assert fact.id in card.evidence_fact_ids
    assert req.id in card.job_requirement_ids
    assert "Built microservices" in card.evidence_claim_texts
    assert "Python microservices required" in card.requirement_texts


def test_build_card_score_contribution_matches_edit() -> None:
    edit = _make_edit(score_contribution=0.08)
    card = build_card(edit, [], [])
    assert card.score_contribution == pytest.approx(0.08)


def test_build_card_edit_cost_matches_edit() -> None:
    edit = _make_edit(edit_cost=0.22)
    card = build_card(edit, [], [])
    assert card.edit_cost == pytest.approx(0.22)


# ── Needs Confirmation controls ───────────────────────────────────────────────


def test_needs_confirmation_card_shows_confirm_reject_controls() -> None:
    """Needs Confirmation cards must include can_confirm and can_reject (Req 8.4)."""
    edit = _make_edit(status=VerificationStatus.NEEDS_CONFIRMATION)
    card = build_card(edit, [], [])
    assert card.can_confirm is True
    assert card.can_reject is True


def test_supported_card_no_confirm_reject_controls() -> None:
    edit = _make_edit(status=VerificationStatus.SUPPORTED)
    card = build_card(edit, [], [])
    assert card.can_confirm is False
    assert card.can_reject is False


def test_unsupported_card_no_confirm_reject_controls() -> None:
    edit = _make_edit(status=VerificationStatus.UNSUPPORTED)
    card = build_card(edit, [], [])
    assert card.can_confirm is False
    assert card.can_reject is False


# ── Aggregate metrics ─────────────────────────────────────────────────────────


def test_aggregate_metrics_total_edit_cost() -> None:
    edits = [
        _make_edit(edit_cost=0.10),
        _make_edit(edit_cost=0.20),
        _make_edit(edit_cost=0.15),
    ]
    agg = build_aggregate(edits)
    assert agg.total_edit_cost == pytest.approx(0.45)


def test_aggregate_metrics_empty_list() -> None:
    agg = build_aggregate([])
    assert agg.total_edit_cost == 0.0
    assert agg.overall_grounding_rate == 0.0
    assert agg.unsupported_claim_rate == 0.0


def test_aggregate_metrics_grounding_rate() -> None:
    edits = [
        _make_edit(status=VerificationStatus.SUPPORTED),
        _make_edit(status=VerificationStatus.PARTIALLY_SUPPORTED),
        _make_edit(status=VerificationStatus.UNSUPPORTED),
        _make_edit(status=VerificationStatus.NEEDS_CONFIRMATION),
    ]
    agg = build_aggregate(edits)
    # 2 grounded out of 4
    assert agg.overall_grounding_rate == pytest.approx(0.5)


def test_aggregate_metrics_unsupported_rate() -> None:
    edits = [
        _make_edit(status=VerificationStatus.SUPPORTED),
        _make_edit(status=VerificationStatus.UNSUPPORTED),
        _make_edit(status=VerificationStatus.UNSUPPORTED),
    ]
    agg = build_aggregate(edits)
    # 2 unsupported out of 3
    assert agg.unsupported_claim_rate == pytest.approx(2 / 3)


def test_aggregate_metrics_projected_decision_pass() -> None:
    edits = [_make_edit()]
    agg = build_aggregate(edits, projected_final_score=0.7, threshold=0.5)
    assert agg.projected_decision == "pass"
    assert agg.projected_final_score == pytest.approx(0.7)


def test_aggregate_metrics_projected_decision_fail() -> None:
    edits = [_make_edit()]
    agg = build_aggregate(edits, projected_final_score=0.3, threshold=0.5)
    assert agg.projected_decision == "fail"


def test_aggregate_metrics_none_when_no_score() -> None:
    edits = [_make_edit()]
    agg = build_aggregate(edits)
    assert agg.projected_final_score is None
    assert agg.projected_decision is None


# ── Confirm / Reject via DB (mocked session) ──────────────────────────────────


def test_confirm_edit_transitions_to_supported() -> None:
    from backend.app.services.explanation_service import confirm_edit

    edit_id = uuid.uuid4()
    mock_edit = MagicMock()
    mock_edit.id = edit_id
    mock_edit.verification_status = MagicMock()
    mock_edit.verification_status.value = VerificationStatus.NEEDS_CONFIRMATION.value

    mock_db = MagicMock()
    mock_db.get.return_value = mock_edit

    result = confirm_edit(db=mock_db, edit_id=edit_id)

    # Status should have been set to SUPPORTED
    assert mock_edit.verification_status == VerificationStatus.SUPPORTED
    mock_db.flush.assert_called_once()


def test_reject_edit_transitions_to_unsupported() -> None:
    from backend.app.services.explanation_service import reject_edit

    edit_id = uuid.uuid4()
    mock_edit = MagicMock()
    mock_edit.id = edit_id
    mock_edit.verification_status = MagicMock()
    mock_edit.verification_status.value = VerificationStatus.NEEDS_CONFIRMATION.value

    mock_db = MagicMock()
    mock_db.get.return_value = mock_edit

    result = reject_edit(db=mock_db, edit_id=edit_id)

    assert mock_edit.verification_status == VerificationStatus.UNSUPPORTED
    mock_db.flush.assert_called_once()


def test_reject_does_not_trigger_regeneration() -> None:
    """
    Reject must NOT call any recourse regeneration function (Req 8.6).
    We verify no recourse_engine module functions are invoked.
    """
    from backend.app.services.explanation_service import reject_edit

    edit_id = uuid.uuid4()
    mock_edit = MagicMock()
    mock_edit.id = edit_id
    mock_edit.verification_status = MagicMock()
    mock_edit.verification_status.value = VerificationStatus.NEEDS_CONFIRMATION.value

    mock_db = MagicMock()
    mock_db.get.return_value = mock_edit

    with patch(
        "backend.app.services.recourse_engine.generate"
    ) as mock_generate:
        reject_edit(db=mock_db, edit_id=edit_id)
        mock_generate.assert_not_called()


def test_confirm_non_needs_confirmation_raises() -> None:
    from backend.app.services.explanation_service import confirm_edit

    edit_id = uuid.uuid4()
    mock_edit = MagicMock()
    mock_edit.id = edit_id
    mock_edit.verification_status = MagicMock()
    mock_edit.verification_status.value = VerificationStatus.SUPPORTED.value

    mock_db = MagicMock()
    mock_db.get.return_value = mock_edit

    with pytest.raises(ValueError, match="Needs Confirmation"):
        confirm_edit(db=mock_db, edit_id=edit_id)


def test_reject_non_needs_confirmation_raises() -> None:
    from backend.app.services.explanation_service import reject_edit

    edit_id = uuid.uuid4()
    mock_edit = MagicMock()
    mock_edit.id = edit_id
    mock_edit.verification_status = MagicMock()
    mock_edit.verification_status.value = VerificationStatus.UNSUPPORTED.value

    mock_db = MagicMock()
    mock_db.get.return_value = mock_edit

    with pytest.raises(ValueError, match="Needs Confirmation"):
        reject_edit(db=mock_db, edit_id=edit_id)


def test_confirm_missing_edit_raises_resource_not_found() -> None:
    from backend.app.exceptions import ResourceNotFoundError
    from backend.app.services.explanation_service import confirm_edit

    mock_db = MagicMock()
    mock_db.get.return_value = None

    with pytest.raises(ResourceNotFoundError):
        confirm_edit(db=mock_db, edit_id=uuid.uuid4())


def test_reject_missing_edit_raises_resource_not_found() -> None:
    from backend.app.exceptions import ResourceNotFoundError
    from backend.app.services.explanation_service import reject_edit

    mock_db = MagicMock()
    mock_db.get.return_value = None

    with pytest.raises(ResourceNotFoundError):
        reject_edit(db=mock_db, edit_id=uuid.uuid4())
