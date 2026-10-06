"""Task 8.2: audit text survives arbitrary valid and invalid PATCH sequences."""

from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from backend.app.models.enums import VerificationStatus
from backend.app.schemas.evidence import CandidateFactPatch
from backend.app.services.evidence_bank import EvidenceBank
from tests.dhruv_support import make_session, seed_evidence

_PATCHES = st.one_of(
    st.builds(
        lambda text: {"claim_text": text}, st.text(alphabet="abc XYZ012", min_size=1, max_size=80)
    ),
    st.builds(
        lambda status: {"verification_status": status},
        st.sampled_from([value.value for value in VerificationStatus]),
    ),
    st.sampled_from(
        [
            {},
            {"claim_text": ""},
            {"claim_text": " "},
            {"verification_status": "invalid"},
            {"claim_text": None},
            {"original_claim_text": "overwrite"},
            {"claim_text": "x" * 2001},
        ]
    ),
)


# Feature: verifiable-counterfactual-recourse, Property 7: original_claim_text immutability
@settings(max_examples=100, deadline=None)
@given(patches=st.lists(_PATCHES, min_size=1, max_size=15))
def test_original_claim_survives_patch_sequences(patches):
    with make_session() as db:
        candidate, facts = seed_evidence(db)
        bank = EvidenceBank(db)
        original = facts[0].original_claim_text
        fact_id = facts[0].id
        for payload in patches:
            before = bank.get_facts(candidate)[0].claim_text
            try:
                patch = CandidateFactPatch.model_validate(payload)
            except ValidationError:
                assert bank.get_facts(candidate)[0].claim_text == before
            else:
                bank.update_fact(candidate, fact_id, patch)
            db.expire_all()
            assert bank.get_facts(candidate)[0].original_claim_text == original
