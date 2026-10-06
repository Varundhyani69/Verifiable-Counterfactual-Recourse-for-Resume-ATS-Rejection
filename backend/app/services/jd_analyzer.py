"""Traceable job requirement extraction using spaCy and domain rules (Task 7)."""

from __future__ import annotations

import os
import re
import uuid
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from backend.app.exceptions import (
    AppError,
    ResourceNotFoundError,
    TextEmptyError,
    TextTooLongError,
)
from backend.app.models.enums import ExtractionType, ImportanceLevel, RequirementType
from backend.app.models.job_description import JobDescription
from backend.app.models.job_requirement import JobRequirement

SKILL_CANON: dict[str, str] = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "py": "Python",
    "python": "Python",
    "java": "Java",
    "c++": "C++",
    "c#": "C#",
    "go": "Go",
    "rust": "Rust",
    "sql": "SQL",
    "nosql": "NoSQL",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "docker": "Docker",
    "k8s": "Kubernetes",
    "kube": "Kubernetes",
    "kubernetes": "Kubernetes",
    "aws": "AWS",
    "gcp": "Google Cloud Platform",
    "azure": "Microsoft Azure",
    "react": "React",
    "angular": "Angular",
    "vue": "Vue.js",
    "vue.js": "Vue.js",
    "node": "Node.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "spring": "Spring",
    "git": "Git",
    "linux": "Linux",
    "html": "HTML",
    "css": "CSS",
    "ci/cd": "CI/CD",
    "rest": "REST",
    "api": "API",
    "graphql": "GraphQL",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "dl": "Deep Learning",
    "deep learning": "Deep Learning",
    "nlp": "Natural Language Processing",
    "natural language processing": "Natural Language Processing",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "pandas": "pandas",
    "numpy": "NumPy",
    "scikit-learn": "scikit-learn",
    "agile": "Agile",
    "scrum": "Scrum",
    "devops": "DevOps",
    "microservices": "Microservices",
}
_SKILLS = re.compile(
    r"(?<![\w])(?:"
    + "|".join(re.escape(k) for k in sorted(SKILL_CANON, key=len, reverse=True))
    + r")(?![\w])",
    re.IGNORECASE,
)
_SIGNALS = re.compile(
    r"\b(must\s+have|required|must|preferred|nice[ -]to[ -]have|desired|plus)\b", re.I
)
_PREFERRED = {"preferred", "nice to have", "desired", "plus"}
_RESPONSIBILITY = re.compile(
    r"\b(develop|design|build|maintain|manage|lead|implement|collaborate|deliver|"
    r"coordinate|support|test|deploy|monitor|mentor|responsibilities|responsible)\b",
    re.I,
)
_CERTIFICATION = re.compile(
    r"\b(certification|certified|certificate|licen[cs]e|cissp|pmp)\b", re.I
)
_QUALIFICATION = re.compile(
    r"\b(degree|bachelor|master|doctorate|ph\.?d|diploma|qualification|graduate)\b", re.I
)
_EXPERIENCE = re.compile(r"\b(experience|\d+\+?\s+years?)\b", re.I)
_SKILL_CUE = re.compile(
    r"\b(skills?|proficien(?:t|cy)|knowledge|familiarity|expertise|competenc(?:e|y))\b", re.I
)
_UNKNOWN_SKILL = re.compile(
    r"(?:\b(?:experience|proficiency|knowledge|familiarity|expertise)\s+(?:in|with|of)|"
    r"\b(?:proficient|skilled)\s+(?:in|with)|\bskills?\s*:)\s*(.+)",
    re.I,
)
_INFERRED_SKILLS = (
    (
        re.compile(r"\b(predictive models?|train(?:ing)? (?:statistical )?models?)\b", re.I),
        "Machine Learning",
    ),
    (re.compile(r"\b(automated tests?|test automation)\b", re.I), "Software Testing"),
)


@lru_cache(maxsize=1)
def _get_nlp() -> Any:
    import spacy

    try:
        return spacy.load(os.environ.get("SPACY_MODEL", "en_core_web_sm"))
    except OSError as exc:
        raise AppError(
            "NLP_UNAVAILABLE", "Install the configured spaCy English model to analyze JDs.", 502
        ) from exc


def normalize_skill(name: str) -> str:
    """Preserve unknown names exactly; normalize only documented aliases."""
    return SKILL_CANON.get(name.casefold(), name)


def _importance(span: Any, inherited: ImportanceLevel) -> ImportanceLevel:
    signals = list(_SIGNALS.finditer(span.text))
    if not signals:
        # The dependency parser can identify inflected modifiers such as 'requires'.
        if any(
            token.lemma_ == "require" and token.dep_ in {"ROOT", "acl", "amod"} for token in span
        ):
            return ImportanceLevel.REQUIRED
        return inherited
    signal = re.sub(r"[ -]+", " ", signals[-1].group().casefold())
    return ImportanceLevel.PREFERRED if signal in _PREFERRED else ImportanceLevel.REQUIRED


def _clauses(doc: Any) -> list[Any]:
    """Split sentences and bullets without losing character offsets or skill lists."""
    clauses = []
    for sentence in doc.sents:
        cursor = sentence.start_char
        separators = re.finditer(
            r"\n+|;|\s+but\s+|(?:,\s*|\s+and\s+)(?=(?:must|required|preferred|"
            r"nice[ -]to[ -]have|desired)\b)",
            sentence.text,
            re.I,
        )
        boundaries = [
            (sentence.start_char + m.start(), sentence.start_char + m.end()) for m in separators
        ]
        # A qualifier on each side must stay with its own skill:
        # "Python required and JS preferred" is two requirements.
        for separator in re.finditer(r",\s*|\s+and\s+", sentence.text, re.I):
            left = re.split(r"[;\n]", sentence.text[: separator.start()])[-1]
            right = re.split(r"[;\n]", sentence.text[separator.end() :])[0]
            if _SIGNALS.search(left) and _SIGNALS.search(right):
                boundaries.append(
                    (
                        sentence.start_char + separator.start(),
                        sentence.start_char + separator.end(),
                    )
                )
        boundaries = sorted(set(boundaries))
        for end, following in [*boundaries, (sentence.end_char, sentence.end_char)]:
            start = cursor
            while start < end and (doc.text[start].isspace() or doc.text[start] in "-•*"):
                start += 1
            while end > start and doc.text[end - 1].isspace():
                end -= 1
            if start < end:
                span = doc.char_span(start, end, alignment_mode="contract")
                if span is not None and span.text.strip():
                    clauses.append(span)
            cursor = following
    return clauses


def _skills(span: Any) -> list[str]:
    matches: list[tuple[int, str]] = [
        (m.start(), normalize_skill(m.group())) for m in _SKILLS.finditer(span.text)
    ]
    for entity in span.ents:
        if entity.label_ in {"SKILL", "PRODUCT", "LANGUAGE", "CERT"}:
            # A configured spaCy entity linker may provide a canonical identifier.
            matches.append(
                (
                    entity.start_char - span.start_char,
                    entity.kb_id_ or normalize_skill(entity.text),
                )
            )
    unknown = _UNKNOWN_SKILL.search(span.text)
    if unknown:
        value = re.sub(
            r"\s+(?:is\s+)?(?:required|preferred|desired|a\s+plus)\b.*$",
            "",
            unknown[1],
            flags=re.I,
        ).strip(" .:")
        for name in re.split(r",\s*|\s+and\s+|\s+or\s+", value):
            name = name.strip()
            if name and not _SKILLS.search(name):
                matches.append((unknown.start(1), normalize_skill(name)))
    return list(dict.fromkeys(name for _, name in sorted(matches, key=lambda item: item[0])))


def _requirement_type(span: Any) -> RequirementType | None:
    for pattern, kind in (
        (_CERTIFICATION, RequirementType.CERTIFICATION),
        (_QUALIFICATION, RequirementType.QUALIFICATION),
        (_EXPERIENCE, RequirementType.EXPERIENCE),
        (_RESPONSIBILITY, RequirementType.RESPONSIBILITY),
        (_SKILL_CUE, RequirementType.SKILL),
    ):
        if pattern.search(span.text):
            return kind
    if any(token.pos_ == "VERB" and _RESPONSIBILITY.fullmatch(token.lemma_) for token in span):
        return RequirementType.RESPONSIBILITY
    return None


class JDAnalyzer:
    def __init__(self, db: Session, nlp: Any = None) -> None:
        self.db = db
        self.nlp = nlp

    def analyze(self, jd_text: str) -> tuple[JobDescription, list[JobRequirement]]:
        if not jd_text.strip():
            raise TextEmptyError("Job description text")
        if len(jd_text) > 10_000:
            raise TextTooLongError("Job description text", 10_000)
        doc = (self.nlp if self.nlp is not None else _get_nlp())(jd_text)
        jd = JobDescription(id=uuid.uuid4(), raw_text=jd_text)
        requirements: list[JobRequirement] = []
        inherited = ImportanceLevel.REQUIRED
        inherited_type: RequirementType | None = None
        for span in _clauses(doc):
            importance = _importance(span, inherited)
            kind = _requirement_type(span)
            skills = _skills(span)
            # Section headings apply only to following items, never become requirements.
            heading = (
                span.text.rstrip().endswith(":")
                and not skills
                and (kind is not None or _SIGNALS.search(span.text))
            )
            if heading:
                inherited = importance
                inherited_type = kind
                continue
            if kind is None and (skills or inherited_type is not None):
                kind = inherited_type or RequirementType.SKILL
            if kind is None and _SIGNALS.search(span.text):
                kind = RequirementType.SKILL
            if kind is None:
                continue
            if not skills and kind == RequirementType.SKILL:
                # Directly named, unmapped skills still retain their original spelling.
                name = _SIGNALS.sub("", span.text).strip(" .:")
                name = re.sub(r"^have\s+|\s+(?:is(?:\s+a)?|a)\s*$", "", name, flags=re.I)
                skills = [normalize_skill(name)] if name.strip() else []
            normalized = skills or [span.text.strip().rstrip(".")]
            requirements.append(self._record(jd, span, kind, importance, normalized))
            # These skills are derived from responsibilities, so expose their inference explicitly.
            if kind == RequirementType.RESPONSIBILITY:
                for pattern, skill in _INFERRED_SKILLS:
                    if pattern.search(span.text) and skill not in skills:
                        requirements.append(
                            self._record(
                                jd,
                                span,
                                RequirementType.SKILL,
                                importance,
                                [skill],
                                ExtractionType.INFERRED,
                            )
                        )
        jd.requirements = requirements
        try:
            self.db.add(jd)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(jd)
        return jd, requirements

    @staticmethod
    def _record(
        jd: JobDescription,
        span: Any,
        kind: RequirementType,
        importance: ImportanceLevel,
        skills: list[str],
        extraction: ExtractionType = ExtractionType.EXPLICIT,
    ) -> JobRequirement:
        return JobRequirement(
            id=uuid.uuid4(),
            job_description_id=jd.id,
            requirement_text=span.text,
            requirement_type=kind,
            importance=importance,
            extraction_type=extraction,
            normalized_skills=skills,
            source_span={"start": span.start_char, "end": span.end_char},
        )

    def get_jd(self, jd_id: uuid.UUID) -> JobDescription:
        jd = self.db.get(JobDescription, jd_id)
        if jd is None:
            raise ResourceNotFoundError("JobDescription", str(jd_id))
        return jd


def analyze(db: Session, jd_text: str) -> tuple[JobDescription, list[JobRequirement]]:
    return JDAnalyzer(db).analyze(jd_text)


def get_jd(db: Session, jd_id: uuid.UUID) -> JobDescription:
    return JDAnalyzer(db).get_jd(jd_id)
