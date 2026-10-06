"""
Unit tests for the Evidence Verifier service.

Covers:
- All 4 decision rule branches with crafted (span, entailment, entities)
- LLM advisory: Unsupported → Needs Confirmation allowed; → Supported forbidden
- methods_used records each method consulted
- rationale is non-empty for every report
- entailment_score clamped to [0.0, 1.0]

Requirements: 7.1–7.8
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models.enums import VerificationStatus
from backend.app.services.verifier import (
    LLMConfig,
    VerificationReport,
    _apply_decision_rules,
    _entailment_score,
    verify_edit,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_fact(
    claim_text: str = "Developed Python microservices",
    source_span: dict | None = None,
) -> MagicMock:
    fact = MagicMock()
    fact.id = uuid.uuid4()
    fact.claim_text = claim_text
    fact.source_span = source_span or {"start": 0, "end": 30}
    fact.candidate_id = uuid.uuid4()
    return fact


def _make_edit(
    proposed_text: str = "Developed Python REST APIs",
    original_text: str = "Built APIs",
    evidence_facts: list | None = None,
) -> MagicMock:
    edit = MagicMock()
    edit.id = uuid.uuid4()
    edit.proposed_text = proposed_text
    edit.original_text = original_text
    edit.evidence_facts = evidence_facts or []
    edit.verification_status = VerificationStatus.NEEDS_CONFIRMATION
    return edit


# ── Decision rule unit tests ──────────────────────────────────────────────────


def test_rule_d_new_entity_always_unsupported() -> None:
    """Rule (d): any new entity → Unsupported regardless of other signals."""
    status = _apply_decision_rules(
        source_span_match=True,
        entail=0.9,  # High entailment
        new_entities={"Amazon"},  # But new entity present
    )
    assert status == VerificationStatus.UNSUPPORTED


def test_rule_a_supported() -> None:
    """Rule (a): span match + entailment ≥ 0.5 + no new entity → Supported."""
    status = _apply_decision_rules(
        source_span_match=True,
        entail=0.75,
        new_entities=set(),
    )
    assert status == VerificationStatus.SUPPORTED


def test_rule_b_partially_supported() -> None:
    """Rule (b): span match + entailment < 0.5 → Partially Supported."""
    status = _apply_decision_rules(
        source_span_match=True,
        entail=0.3,
        new_entities=set(),
    )
    assert status == VerificationStatus.PARTIALLY_SUPPORTED


def test_rule_c_needs_confirmation() -> None:
    """Rule (c): no span match + entailment ≥ 0.5 → Needs Confirmation."""
    status = _apply_decision_rules(
        source_span_match=False,
        entail=0.6,
        new_entities=set(),
    )
    assert status == VerificationStatus.NEEDS_CONFIRMATION


def test_rule_default_needs_confirmation() -> None:
    """Default: no span match + low entailment + no new entity → Needs Confirmation."""
    status = _apply_decision_rules(
        source_span_match=False,
        entail=0.2,
        new_entities=set(),
    )
    assert status == VerificationStatus.NEEDS_CONFIRMATION


def test_rule_d_priority_over_rule_a() -> None:
    """Rule (d) takes priority: new entity + high entail + span → Unsupported."""
    status = _apply_decision_rules(
        source_span_match=True,
        entail=1.0,
        new_entities={"NewCorp"},
    )
    assert status == VerificationStatus.UNSUPPORTED


def test_rule_a_boundary_entailment_exactly_half() -> None:
    """Boundary: entailment == 0.5 with span match → Supported (≥ 0.5)."""
    status = _apply_decision_rules(
        source_span_match=True,
        entail=0.5,
        new_entities=set(),
    )
    assert status == VerificationStatus.SUPPORTED


# ── verify_edit with mocked NLP ───────────────────────────────────────────────


@patch("backend.app.services.verifier._get_nli")
@patch("backend.app.services.verifier._get_nlp")
def test_verify_edit_returns_report_with_non_empty_rationale(
    mock_nlp: MagicMock, mock_nli: MagicMock
) -> None:
    # spaCy: no entities
    nlp_mock = MagicMock()
    doc_mock = MagicMock()
    doc_mock.ents = []
    nlp_mock.return_value = doc_mock
    mock_nlp.return_value = nlp_mock

    # NLI: entailment = 0.7
    nli_mock = MagicMock()
    import numpy as np
    nli_mock.predict.return_value = np.array([[0.1, 0.7, 0.2]])
    mock_nli.return_value = nli_mock

    fact = _make_fact()
    edit = _make_edit(evidence_facts=[fact])

    report = verify_edit(edit, [fact])
    assert isinstance(report, VerificationReport)
    assert len(report.rationale) > 0


@patch("backend.app.services.verifier._get_nli")
@patch("backend.app.services.verifier._get_nlp")
def test_verify_edit_methods_used_populated(
    mock_nlp: MagicMock, mock_nli: MagicMock
) -> None:
    nlp_mock = MagicMock()
    doc_mock = MagicMock()
    doc_mock.ents = []
    nlp_mock.return_value = doc_mock
    mock_nlp.return_value = nlp_mock

    nli_mock = MagicMock()
    import numpy as np
    nli_mock.predict.return_value = np.array([[0.1, 0.6, 0.3]])
    mock_nli.return_value = nli_mock

    fact = _make_fact()
    edit = _make_edit(evidence_facts=[fact])
    report = verify_edit(edit, [fact])

    assert "source_span_match" in report.methods_used
    assert "entity_check" in report.methods_used
    assert "entailment" in report.methods_used


@patch("backend.app.services.verifier._get_nli")
@patch("backend.app.services.verifier._get_nlp")
def test_verify_edit_entailment_clamped_to_range(
    mock_nlp: MagicMock, mock_nli: MagicMock
) -> None:
    nlp_mock = MagicMock()
    doc_mock = MagicMock()
    doc_mock.ents = []
    nlp_mock.return_value = doc_mock
    mock_nlp.return_value = nlp_mock

    nli_mock = MagicMock()
    import numpy as np
    # Deliberately return logits that after softmax exceed 1 — should be clamped
    nli_mock.predict.return_value = np.array([[0.0, 1.5, 0.0]])
    mock_nli.return_value = nli_mock

    fact = _make_fact()
    edit = _make_edit(evidence_facts=[fact])
    report = verify_edit(edit, [fact])

    assert 0.0 <= report.entailment_score <= 1.0


@patch("backend.app.services.verifier._get_nli")
@patch("backend.app.services.verifier._get_nlp")
def test_verify_edit_evidence_fact_ids_match(
    mock_nlp: MagicMock, mock_nli: MagicMock
) -> None:
    nlp_mock = MagicMock()
    doc_mock = MagicMock()
    doc_mock.ents = []
    nlp_mock.return_value = doc_mock
    mock_nlp.return_value = nlp_mock

    nli_mock = MagicMock()
    import numpy as np
    nli_mock.predict.return_value = np.array([[0.1, 0.7, 0.2]])
    mock_nli.return_value = nli_mock

    fact1 = _make_fact("Worked with Python")
    fact2 = _make_fact("Used FastAPI")
    edit = _make_edit(evidence_facts=[fact1, fact2])

    report = verify_edit(edit, [fact1, fact2])
    assert fact1.id in report.evidence_fact_ids
    assert fact2.id in report.evidence_fact_ids


# ── LLM advisory constraints ──────────────────────────────────────────────────


@patch("backend.app.services.verifier._get_nli")
@patch("backend.app.services.verifier._get_nlp")
def test_llm_advisory_included_in_methods_when_enabled(
    mock_nlp: MagicMock, mock_nli: MagicMock
) -> None:
    nlp_mock = MagicMock()
    doc_mock = MagicMock()
    doc_mock.ents = []
    nlp_mock.return_value = doc_mock
    mock_nlp.return_value = nlp_mock

    nli_mock = MagicMock()
    import numpy as np
    nli_mock.predict.return_value = np.array([[0.1, 0.7, 0.2]])
    mock_nli.return_value = nli_mock

    fact = _make_fact()
    edit = _make_edit(evidence_facts=[fact])
    llm_cfg = LLMConfig(enabled=True)

    report = verify_edit(edit, [fact], llm_config=llm_cfg)
    assert "llm_advisory" in report.methods_used


@patch("backend.app.services.verifier._get_nli")
@patch("backend.app.services.verifier._get_nlp")
def test_llm_advisory_cannot_produce_supported(
    mock_nlp: MagicMock, mock_nli: MagicMock
) -> None:
    """
    Even with LLM advisory enabled, when no span match and low entailment,
    the result must NOT be Supported (only Unsupported → Needs Confirmation
    upgrade is allowed).
    """
    # NLP returns a new entity not in evidence → rule (d) fires → Unsupported
    nlp_mock = MagicMock()

    # First call (proposed_text): returns one new entity
    proposed_ent = MagicMock()
    proposed_ent.text = "UnknownCorp"

    # Subsequent calls (fact texts): no entities
    def nlp_side_effect(text: str) -> MagicMock:
        doc = MagicMock()
        if "UnknownCorp" in text:
            doc.ents = [proposed_ent]
        else:
            doc.ents = []
        return doc

    nlp_mock.side_effect = nlp_side_effect
    mock_nlp.return_value = nlp_mock

    nli_mock = MagicMock()
    import numpy as np
    nli_mock.predict.return_value = np.array([[0.0, 0.05, 0.95]])  # very low entailment
    mock_nli.return_value = nli_mock

    fact = _make_fact("Worked at a previous company")
    edit = _make_edit(
        proposed_text="Worked at UnknownCorp as a Python developer",
        evidence_facts=[fact],
    )
    llm_cfg = LLMConfig(enabled=True)

    report = verify_edit(edit, [fact], llm_config=llm_cfg)

    # LLM advisory can at most upgrade Unsupported → Needs Confirmation,
    # never to Supported or Partially Supported.
    assert report.assigned_status not in (
        VerificationStatus.SUPPORTED.value,
        VerificationStatus.PARTIALLY_SUPPORTED.value,
    )


# ── No facts edge case ────────────────────────────────────────────────────────


@patch("backend.app.services.verifier._get_nli")
@patch("backend.app.services.verifier._get_nlp")
def test_verify_edit_no_facts(
    mock_nlp: MagicMock, mock_nli: MagicMock
) -> None:
    nlp_mock = MagicMock()
    doc_mock = MagicMock()
    doc_mock.ents = []
    nlp_mock.return_value = doc_mock
    mock_nlp.return_value = nlp_mock

    nli_mock = MagicMock()
    import numpy as np
    nli_mock.predict.return_value = np.array([[0.3, 0.3, 0.4]])
    mock_nli.return_value = nli_mock

    edit = _make_edit(evidence_facts=[])
    report = verify_edit(edit, [])
    # Should still return a report without crashing
    assert isinstance(report, VerificationReport)
    assert report.entailment_score == 0.0  # no facts → no entailment
