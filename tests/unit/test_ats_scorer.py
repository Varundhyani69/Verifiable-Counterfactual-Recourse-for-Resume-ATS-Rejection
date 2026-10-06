"""
Unit tests for the ATS scorer service.

Covers:
- total_score ∈ [0.0, 1.0] with boundary inputs
- weights summing to ≠ 1.0 raises ValueError (→ 422 in API layer)
- decision == "pass" iff total_score >= threshold (including equality)
- 502 error response shape when SBERT fails (mocked)
- disclosure string always present

Requirements: 4.1–4.9
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from backend.app.services.ats_scorer import (
    DISCLOSURE,
    ScoringConfig,
    _skill_overlap,
    score,
)


# ── ScoringConfig validation ──────────────────────────────────────────────────


def test_scoring_config_default_sums_to_one() -> None:
    cfg = ScoringConfig()
    assert abs(cfg.skill_overlap_weight + cfg.sbert_weight - 1.0) < 1e-9


def test_scoring_config_weights_not_summing_to_one_raises() -> None:
    with pytest.raises(ValueError, match="must equal 1.0"):
        ScoringConfig(skill_overlap_weight=0.6, sbert_weight=0.6)


def test_scoring_config_valid_custom_weights() -> None:
    cfg = ScoringConfig(skill_overlap_weight=0.3, sbert_weight=0.7)
    assert cfg.skill_overlap_weight == 0.3
    assert cfg.sbert_weight == 0.7


def test_scoring_config_threshold_at_boundaries() -> None:
    cfg_low = ScoringConfig(threshold=0.0)
    cfg_high = ScoringConfig(threshold=1.0)
    assert cfg_low.threshold == 0.0
    assert cfg_high.threshold == 1.0


# ── Skill overlap sub-component ───────────────────────────────────────────────


def test_skill_overlap_identical_texts() -> None:
    text = "Python machine learning data science"
    result = _skill_overlap(text, text)
    # Identical sets → union == intersection → should be 1.0
    assert result == 1.0


def test_skill_overlap_no_common_tokens() -> None:
    result = _skill_overlap("Java Spring Hibernate", "React Vue Angular")
    assert 0.0 <= result <= 1.0


def test_skill_overlap_empty_texts() -> None:
    # Both empty → both sets empty → 0.0
    result = _skill_overlap("", "")
    assert result == 0.0


def test_skill_overlap_partial_match() -> None:
    result = _skill_overlap("Python Java SQL", "Python TypeScript SQL")
    assert 0.0 < result < 1.0


# ── Score range invariant ─────────────────────────────────────────────────────


def _make_mock_sbert() -> MagicMock:
    """Return a mocked SentenceTransformer that returns fixed embeddings."""
    import numpy as np
    mock = MagicMock()
    # Return two unit vectors that are identical (cosine = 1.0)
    vec = np.array([1.0, 0.0, 0.0])
    mock.encode.return_value = np.array([vec, vec])
    return mock


@patch("backend.app.services.ats_scorer._get_sbert")
def test_total_score_in_range(mock_get_sbert: MagicMock) -> None:
    mock_get_sbert.return_value = _make_mock_sbert()
    cfg = ScoringConfig()
    result = score("Python developer", "Python developer", cfg)
    assert 0.0 <= result.total_score <= 1.0


@patch("backend.app.services.ats_scorer._get_sbert")
def test_total_score_empty_inputs(mock_get_sbert: MagicMock) -> None:
    import numpy as np
    mock = MagicMock()
    mock.encode.return_value = np.array([np.zeros(3), np.zeros(3)])
    mock_get_sbert.return_value = mock

    cfg = ScoringConfig()
    result = score("", "", cfg)
    assert 0.0 <= result.total_score <= 1.0


# ── Decision invariant ────────────────────────────────────────────────────────


@patch("backend.app.services.ats_scorer._get_sbert")
def test_decision_pass_when_score_equals_threshold(mock_get_sbert: MagicMock) -> None:
    """Equality with threshold → 'pass'."""
    import numpy as np
    # Force total_score == threshold by controlling both components
    # We'll set threshold = 0.5 and mock both to give exactly 0.5
    mock = MagicMock()
    # Construct embeddings whose cosine is 1.0 so semantic sim = 1.0
    vec = np.array([1.0, 0.0, 0.0])
    mock.encode.return_value = np.array([vec, vec])
    mock_get_sbert.return_value = mock

    # skill_overlap == 1.0, semantic == 1.0, total == 1.0 * 0.5 + 1.0 * 0.5 = 1.0
    cfg = ScoringConfig(threshold=1.0)
    result = score("python", "python", cfg)
    # total_score should be 1.0 >= threshold 1.0
    assert result.decision == "pass"
    assert result.total_score >= cfg.threshold


@patch("backend.app.services.ats_scorer._get_sbert")
def test_decision_fail_when_score_below_threshold(mock_get_sbert: MagicMock) -> None:
    import numpy as np
    mock = MagicMock()
    # Orthogonal vectors → cosine = 0.0
    mock.encode.return_value = np.array(
        [np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])]
    )
    mock_get_sbert.return_value = mock

    cfg = ScoringConfig(threshold=0.99)  # Very high threshold
    result = score("some resume text", "completely different jd", cfg)
    assert result.decision == "fail"
    assert result.total_score < cfg.threshold


@patch("backend.app.services.ats_scorer._get_sbert")
def test_decision_consistent_with_score(mock_get_sbert: MagicMock) -> None:
    """decision == 'pass' iff total_score >= threshold."""
    import numpy as np
    mock = MagicMock()
    vec = np.array([1.0, 0.0, 0.0])
    mock.encode.return_value = np.array([vec, vec])
    mock_get_sbert.return_value = mock

    cfg = ScoringConfig(threshold=0.5)
    result = score("Python developer 5 years", "Python developer required", cfg)

    if result.total_score >= cfg.threshold:
        assert result.decision == "pass"
    else:
        assert result.decision == "fail"


# ── Disclosure string ─────────────────────────────────────────────────────────


@patch("backend.app.services.ats_scorer._get_sbert")
def test_disclosure_always_present(mock_get_sbert: MagicMock) -> None:
    import numpy as np
    mock = MagicMock()
    vec = np.array([1.0, 0.0, 0.0])
    mock.encode.return_value = np.array([vec, vec])
    mock_get_sbert.return_value = mock

    cfg = ScoringConfig()
    result = score("resume", "job description", cfg)
    assert result.disclosure == DISCLOSURE
    assert len(result.disclosure) > 0


# ── SBERT failure → RuntimeError ─────────────────────────────────────────────


@patch("backend.app.services.ats_scorer._get_sbert")
def test_sbert_failure_raises_runtime_error(mock_get_sbert: MagicMock) -> None:
    """
    When SBERT encoding fails, score() must raise RuntimeError.
    The API layer converts this to a 502 response.
    """
    mock = MagicMock()
    mock.encode.side_effect = Exception("SBERT OOM")
    mock_get_sbert.return_value = mock

    cfg = ScoringConfig()
    with pytest.raises(RuntimeError, match="SBERT"):
        score("resume text", "jd text", cfg)


# ── Weights in ScoreResult ────────────────────────────────────────────────────


@patch("backend.app.services.ats_scorer._get_sbert")
def test_score_result_contains_weights(mock_get_sbert: MagicMock) -> None:
    import numpy as np
    mock = MagicMock()
    vec = np.array([1.0, 0.0, 0.0])
    mock.encode.return_value = np.array([vec, vec])
    mock_get_sbert.return_value = mock

    cfg = ScoringConfig(skill_overlap_weight=0.4, sbert_weight=0.6)
    result = score("Python", "Python", cfg)
    assert "skill_overlap" in result.weights
    assert "sbert" in result.weights
    assert result.weights["skill_overlap"] == pytest.approx(0.4)
    assert result.weights["sbert"] == pytest.approx(0.6)
