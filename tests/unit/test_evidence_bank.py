"""Task 8.3: evidence scoping, validation, usable facts and audit trail."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.app.exceptions import ResourceNotFoundError
from backend.app.models.enums import VerificationStatus
from backend.app.schemas.evidence import CandidateFactPatch
from backend.app.services.evidence_bank import EvidenceBank
from tests.dhruv_support import make_session, seed_evidence


@pytest.fixture
def bank():
    with make_session() as db:
        yield EvidenceBank(db)


def test_get_and_usable_facts(bank):
    candidate, facts = seed_evidence(bank.db, tuple(VerificationStatus))
    assert {f.id for f in bank.get_facts(candidate)} == {f.id for f in facts}
    usable = bank.get_usable_facts(candidate)
    assert len(usable) == 3
    assert all(f.verification_status != VerificationStatus.UNSUPPORTED for f in usable)


def test_update_preserves_audit_and_metadata(bank):
    candidate, facts = seed_evidence(bank.db)
    fact = facts[0]
    fact.updated_at = datetime(2020, 1, 1, tzinfo=UTC)
    bank.db.commit()
    original = fact.original_claim_text
    for value in ("Created Python APIs.", "Developed REST APIs."):
        updated = bank.update_fact(candidate, fact.id, CandidateFactPatch(claim_text=value))
        assert updated.claim_text == value
        assert updated.original_claim_text == original
        assert updated.updated_at.year > 2020
        assert updated.metadata_ == {"skills": ["Python"], "projects": ["API"]}
    updated = bank.update_fact(
        candidate, fact.id, CandidateFactPatch(verification_status="Supported")
    )
    assert updated.verification_status == VerificationStatus.SUPPORTED
    assert updated.claim_text == "Developed REST APIs."
    assert updated.original_claim_text == original


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"claim_text": ""},
        {"claim_text": " \n"},
        {"claim_text": "a" * 2001},
        {"verification_status": "fake"},
        {"claim_text": None},
        {"verification_status": None},
        {"original_claim_text": "overwrite"},
        {"metadata": {}},
        {"claim_text": 123},
    ],
)
def test_patch_rejects_invalid_values(payload):
    with pytest.raises(ValidationError):
        CandidateFactPatch.model_validate(payload)


@pytest.mark.parametrize("text", ["x", "x" * 2000])
def test_patch_boundaries(bank, text):
    candidate, facts = seed_evidence(bank.db)
    assert (
        bank.update_fact(candidate, facts[0].id, CandidateFactPatch(claim_text=text)).claim_text
        == text
    )


def test_other_candidates_fact_cannot_be_updated(bank):
    candidate, facts = seed_evidence(bank.db)
    with pytest.raises(ResourceNotFoundError):
        bank.update_fact(uuid.uuid4(), facts[0].id, CandidateFactPatch(claim_text="tampered"))
    assert bank.get_facts(candidate)[0].claim_text == "Developed Python APIs."


def test_missing_candidate_and_fact(bank):
    with pytest.raises(ResourceNotFoundError):
        bank.get_facts(uuid.uuid4())
    candidate, _ = seed_evidence(bank.db)
    with pytest.raises(ResourceNotFoundError):
        bank.update_fact(candidate, uuid.uuid4(), CandidateFactPatch(claim_text="valid"))


def test_known_candidate_with_no_facts(bank):
    candidate, _ = seed_evidence(bank.db, ())
    assert bank.get_facts(candidate) == []
    assert bank.get_usable_facts(candidate) == []
