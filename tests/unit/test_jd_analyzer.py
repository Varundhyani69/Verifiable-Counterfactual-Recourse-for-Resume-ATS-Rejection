"""Task 7.4: requirement coverage, NLP extraction, validation and persistence."""

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

from backend.app.exceptions import ResourceNotFoundError, TextEmptyError, TextTooLongError
from backend.app.models.enums import ExtractionType, ImportanceLevel, RequirementType
from backend.app.models.job_description import JobDescription
from backend.app.services.jd_analyzer import JDAnalyzer, normalize_skill
from tests.dhruv_support import make_nlp, make_session


@pytest.fixture
def analyzer():
    with make_session() as db:
        yield JDAnalyzer(db, nlp=make_nlp())


@pytest.mark.parametrize(
    "signal,expected",
    [
        ("must have", "required"),
        ("required", "required"),
        ("must", "required"),
        ("preferred", "preferred"),
        ("nice to have", "preferred"),
        ("desired", "preferred"),
        ("plus", "preferred"),
        ("nice-to-have", "preferred"),
        ("", "required"),
    ],
)
def test_signal_mapping(analyzer, signal, expected):
    _, requirements = analyzer.analyze(f"Python {signal}")
    assert len(requirements) == 1
    assert requirements[0].importance == expected


def test_all_categories_and_round_trip(analyzer):
    text = (
        "Must have JS skills. Docker preferred. Develop backend services. "
        "Bachelor degree required. 5+ years Python experience. AWS certification desired."
    )
    jd, requirements = analyzer.analyze(text)
    assert {r.requirement_type for r in requirements} == set(RequirementType)
    assert "JavaScript" in requirements[0].normalized_skills
    assert analyzer.get_jd(jd.id).raw_text == text
    analyzer.db.expire_all()
    assert len(analyzer.get_jd(jd.id).requirements) == len(requirements)
    for requirement in requirements:
        span = requirement.source_span
        assert 0 <= span["start"] < span["end"] <= len(text)
        assert text[span["start"] : span["end"]] == requirement.requirement_text


@pytest.mark.parametrize(
    "text",
    [
        "Experience with QuantumWidget",
        "Must have QuantumWidget",
        "QuantumWidget preferred",
        "QuantumWidget is a plus",
    ],
)
def test_unknown_skill_preserved(analyzer, text):
    _, requirements = analyzer.analyze(text)
    assert requirements[0].normalized_skills == ["QuantumWidget"]
    assert normalize_skill("Unmapped Skill") == "Unmapped Skill"


def test_ner_skill_extraction(analyzer):
    _, requirements = analyzer.analyze("Zig")
    assert requirements[0].normalized_skills == ["Zig"]


def test_explicit_and_inferred_requirements(analyzer):
    _, requirements = analyzer.analyze("Build predictive models.")
    assert [r.extraction_type for r in requirements] == [
        ExtractionType.EXPLICIT,
        ExtractionType.INFERRED,
    ]
    assert requirements[1].normalized_skills == ["Machine Learning"]


def test_heading_and_mixed_importance_scoping(analyzer):
    _, requirements = analyzer.analyze(
        "Preferred skills:\nPython\nJS\nRequired skills:\nDocker\n"
        "Must have SQL, preferred Rust; Kubernetes required."
    )
    assert [r.importance for r in requirements] == [
        ImportanceLevel.PREFERRED,
        ImportanceLevel.PREFERRED,
        ImportanceLevel.REQUIRED,
        ImportanceLevel.REQUIRED,
        ImportanceLevel.PREFERRED,
        ImportanceLevel.REQUIRED,
    ]


def test_skill_lists_and_punctuation(analyzer):
    _, requirements = analyzer.analyze("Must have C++, C#, Node.js and JS.")
    skills = [skill for requirement in requirements for skill in requirement.normalized_skills]
    assert skills == ["C++", "C#", "Node.js", "JavaScript"]


@pytest.mark.parametrize(
    "text", ["Python required and JS preferred", "Must have Python and JS preferred"]
)
def test_conjoined_requirements_keep_their_qualifiers(analyzer, text):
    _, requirements = analyzer.analyze(text)
    assert [r.normalized_skills for r in requirements] == [["Python"], ["JavaScript"]]
    assert [r.importance for r in requirements] == ["required", "preferred"]


def test_real_spacy_pipeline():
    model = pytest.importorskip("en_core_web_sm")
    with make_session() as db:
        analyzer = JDAnalyzer(db, model.load())
        text = "Python required and JS preferred. Developing predictive models."
        _, requirements = analyzer.analyze(text)
        assert [r.importance for r in requirements[:2]] == ["required", "preferred"]
        assert any(r.extraction_type == ExtractionType.INFERRED for r in requirements)
        for requirement in requirements:
            span = requirement.source_span
            assert text[span["start"] : span["end"]] == requirement.requirement_text


def test_no_requirements_still_persists(analyzer):
    jd, requirements = analyzer.analyze("Welcome to our company.")
    assert requirements == []
    assert analyzer.get_jd(jd.id).raw_text == "Welcome to our company."


@pytest.mark.parametrize(
    "text,error",
    [("", TextEmptyError), (" \n\t", TextEmptyError), ("a" * 10_001, TextTooLongError)],
)
def test_invalid_input_does_not_persist(analyzer, text, error):
    with pytest.raises(error):
        analyzer.analyze(text)
    assert analyzer.db.scalar(select(func.count()).select_from(JobDescription)) == 0


def test_maximum_length_accepted(analyzer):
    jd, _ = analyzer.analyze("Python" + " " * 9994)
    assert len(jd.raw_text) == 10_000


def test_missing_jd(analyzer):
    with pytest.raises(ResourceNotFoundError):
        analyzer.get_jd(uuid.uuid4())


def test_failed_commit_rolls_back():
    db = MagicMock()
    db.commit.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError):
        JDAnalyzer(db, make_nlp()).analyze("Python required")
    db.rollback.assert_called_once()
