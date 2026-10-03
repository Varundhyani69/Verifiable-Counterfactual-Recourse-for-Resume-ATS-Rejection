"""
Property test — source span validity (Property 1, Task 5.2).

Feature: verifiable-counterfactual-recourse, Property 1:
    Every source span satisfies 0 ≤ start < end ≤ len(extracted_text).

Validates: Requirements 1.2, 2.4, 3.2
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.models.enums import DocumentType
from backend.app.models.resume_document import ResumeDocument

# Generate arbitrary non-empty strings for document text
_text_strategy = st.text(min_size=1, max_size=2000, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z"),
))


def _make_resume(text: str) -> ResumeDocument:
    """Create a ResumeDocument with the given text."""
    return ResumeDocument(
        id=uuid.uuid4(),
        candidate_id=uuid.uuid4(),
        extracted_text=text,
        document_type=DocumentType.MANUAL,
        filename=None,
        source_spans=[{"start": 0, "end": len(text), "text": text}],
    )


def _make_db_mock():
    db = MagicMock()
    def _refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()
    db.refresh.side_effect = _refresh
    return db


@pytest.fixture(autouse=True)
def _check_spacy():
    try:
        import spacy
        spacy.load("en_core_web_sm")
    except (ImportError, OSError):
        pytest.skip("spaCy model 'en_core_web_sm' not installed")


@given(text=_text_strategy)
@settings(max_examples=100, deadline=None)
def test_source_span_validity(text: str) -> None:
    """
    Feature: verifiable-counterfactual-recourse, Property 1:
    Every source span satisfies 0 ≤ start < end ≤ len(extracted_text).
    """
    from backend.app.services import evidence_extractor

    db = _make_db_mock()
    resume = _make_resume(text)
    facts = evidence_extractor.extract(db=db, resume=resume)

    text_len = len(text)
    for fact in facts:
        span = fact.source_span
        assert span["start"] >= 0, f"start < 0: {span}"
        assert span["start"] < span["end"], f"start >= end: {span}"
        assert span["end"] <= text_len, f"end > len(text): {span}, len={text_len}"
