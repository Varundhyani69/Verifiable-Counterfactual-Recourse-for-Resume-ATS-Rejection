"""Tasks 7.2/7.3: importance, skill normalization and source-span invariants."""

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.services.jd_analyzer import JDAnalyzer
from tests.dhruv_support import make_nlp, make_session

_NLP = make_nlp()
_SIGNALS = st.sampled_from(
    ["", "must have", "required", "must", "preferred", "nice to have", "desired", "plus"]
)
_SKILLS = st.sampled_from(["JS", "Python", "C++", "C#", "k8s", "Zig", "QuantumWidget"])


# Feature: verifiable-counterfactual-recourse, Property 4: JobRequirement importance invariant
@settings(max_examples=100, deadline=None)
@given(signal=_SIGNALS, skill=_SKILLS, padding=st.text(alphabet=" \n\t", min_size=0, max_size=20))
def test_requirement_importance(signal, skill, padding):
    text = f"{padding}Knowledge of {skill} {signal}"
    with make_session() as db:
        _, requirements = JDAnalyzer(db, _NLP).analyze(text)
        assert requirements
        expected = (
            "preferred"
            if signal in {"preferred", "nice to have", "desired", "plus"}
            else "required"
        )
        for requirement in requirements:
            assert requirement.importance in {"required", "preferred"}
            assert requirement.importance == expected
            span = requirement.source_span
            assert 0 <= span["start"] < span["end"] <= len(text)
            assert text[span["start"] : span["end"]] == requirement.requirement_text


# Feature: verifiable-counterfactual-recourse, Property 5: Skill normalization completeness
@settings(max_examples=100, deadline=None)
@given(
    name=st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", min_size=1, max_size=30
    )
)
def test_normalization_completeness(name):
    with make_session() as db:
        _, requirements = JDAnalyzer(db, _NLP).analyze(f"Experience with {name}")
        assert requirements
        for requirement in requirements:
            assert requirement.normalized_skills
            assert all(
                isinstance(skill, str) and skill.strip() for skill in requirement.normalized_skills
            )
