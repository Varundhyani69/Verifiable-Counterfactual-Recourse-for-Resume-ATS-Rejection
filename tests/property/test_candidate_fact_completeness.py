"""
Property test — CandidateFact field completeness (Property 6, Task 6.2).

Feature: verifiable-counterfactual-recourse, Property 6:
    For any auto-extracted CandidateFact, all nine required fields must be present
    and non-null: id, candidate_id, claim_text, claim_type, source_document_id,
    source_span, verification_status, original_claim_text, metadata.
    The verification_status must equal "Needs Confirmation" at creation time.

Validates: Requirements 3.2, 3.3
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.models.enums import DocumentType, VerificationStatus
from backend.app.models.resume_document import ResumeDocument
from backend.app.services import evidence_extractor

try:
    import spacy
    spacy.load("en_core_web_sm")
    _SPACY_AVAILABLE = True
except (ImportError, OSError):
    _SPACY_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _SPACY_AVAILABLE, reason="spaCy model 'en_core_web_sm' not installed"
)

# Strategy to generate varied resume texts
_resume_text_samples = st.sampled_from([
    "Skills: Python, TypeScript, Docker, SQL, Kubernetes, AWS.",
    "Led a team of 15 engineers to redesign the payment processing architecture.",
    "Created an automated CI/CD pipeline reducing build times by 45%.",
    "Certified Kubernetes Administrator (CKA) and AWS Solutions Architect.",
    "Senior Software Engineer at Google from 2020 to 2024.",
    "Increased system throughput by 300% while reducing latency by 40ms.",
    "Developed a distributed caching service using Redis and Golang.",
    "Bachelor of Science in Computer Science, Stanford University.",
])


def _make_db_mock():
    db = MagicMock()

    def _refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()

    db.refresh.side_effect = _refresh
    return db


@given(text=_resume_text_samples)
@settings(max_examples=50, deadline=None)
def test_candidate_fact_field_completeness(text: str):
    """
    Every extracted CandidateFact must have all 9 required fields present and non-null,
    and verification_status == "Needs Confirmation".
    """
    db = _make_db_mock()
    resume = ResumeDocument(
        id=uuid.uuid4(),
        candidate_id=uuid.uuid4(),
        extracted_text=text,
        document_type=DocumentType.MANUAL,
        filename=None,
        source_spans=[{"start": 0, "end": len(text), "text": text}],
    )

    facts = evidence_extractor.extract(db=db, resume=resume)

    for fact in facts:
        # 1. id
        assert fact.id is not None, "fact.id must not be None"
        # 2. candidate_id
        assert fact.candidate_id is not None, "fact.candidate_id must not be None"
        assert fact.candidate_id == resume.candidate_id
        # 3. claim_text
        assert fact.claim_text is not None, "fact.claim_text must not be None"
        assert len(fact.claim_text) > 0
        # 4. claim_type
        assert fact.claim_type is not None, "fact.claim_type must not be None"
        # 5. source_document_id
        assert fact.source_document_id is not None, "fact.source_document_id must not be None"
        assert fact.source_document_id == resume.id
        # 6. source_span
        assert fact.source_span is not None, "fact.source_span must not be None"
        assert "start" in fact.source_span and "end" in fact.source_span
        # 7. verification_status
        assert fact.verification_status is not None, "fact.verification_status must not be None"
        assert fact.verification_status == VerificationStatus.NEEDS_CONFIRMATION
        # 8. original_claim_text
        assert fact.original_claim_text is not None, "fact.original_claim_text must not be None"
        assert fact.original_claim_text == fact.claim_text
        # 9. metadata
        assert fact.metadata_ is not None, "fact.metadata_ must not be None"
        assert isinstance(fact.metadata_, dict)
