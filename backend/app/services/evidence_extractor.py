"""
Evidence extractor service.

Uses spaCy NER pipeline to extract discrete candidate facts from resume text.
Each extracted fact is classified into one of 6 claim types and stored with
``verification_status = "Needs Confirmation"`` (Req 3.3).

Triggered automatically on successful ingestion (Task 5).

Public API:
    extract(db, resume) → list[CandidateFact]

Requirements: 3.1, 3.2, 3.3
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.candidate_fact import CandidateFact
from backend.app.models.enums import ClaimType, VerificationStatus
from backend.app.models.resume_document import ResumeDocument

# ── spaCy model config ────────────────────────────────────────────────────────

SPACY_MODEL: str = os.environ.get("SPACY_MODEL", "en_core_web_sm")

# ── Entity-label → ClaimType mapping ─────────────────────────────────────────
# spaCy NER labels mapped to our domain claim types.
# Labels not in this map are silently skipped.
_LABEL_TO_CLAIM_TYPE: dict[str, ClaimType] = {
    # Technical / domain skills
    "SKILL": ClaimType.SKILL,
    "PRODUCT": ClaimType.SKILL,
    "LANGUAGE": ClaimType.SKILL,
    # Work experience & organizations
    "ORG": ClaimType.EXPERIENCE,
    "WORK_OF_ART": ClaimType.PROJECT,
    # Certifications
    "CERT": ClaimType.CERTIFICATION,
    # Dates, events, and quantities (used as experience markers)
    "DATE": ClaimType.EXPERIENCE,
    "EVENT": ClaimType.ACHIEVEMENT,
    # Cardinal numbers / percentages often signal achievements
    "CARDINAL": ClaimType.ACHIEVEMENT,
    "PERCENT": ClaimType.ACHIEVEMENT,
    "MONEY": ClaimType.ACHIEVEMENT,
    "QUANTITY": ClaimType.ACHIEVEMENT,
    # Catch-all for unrecognised entities that still carry signal
    "GPE": ClaimType.EXPERIENCE,       # geo-political entities → experience location
    "NORP": ClaimType.EXPERIENCE,      # nationalities / groups
    "FAC": ClaimType.PROJECT,          # facilities / buildings
    "LOC": ClaimType.EXPERIENCE,       # locations
    "LAW": ClaimType.CERTIFICATION,    # laws / regulations
    "ORDINAL": ClaimType.ACHIEVEMENT,  # ordinal numbers
}

# ── Keyword-based extraction patterns ────────────────────────────────────────
# These simple heuristics augment spaCy NER for resume-specific claim types
# that standard NER models often miss.

_SKILL_KEYWORDS: set[str] = {
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
    "sql", "nosql", "mongodb", "postgresql", "mysql", "redis", "docker",
    "kubernetes", "aws", "azure", "gcp", "react", "angular", "vue", "node",
    "flask", "django", "fastapi", "spring", "tensorflow", "pytorch", "pandas",
    "numpy", "scikit-learn", "machine learning", "deep learning", "nlp",
    "data science", "devops", "ci/cd", "agile", "scrum", "git", "linux",
    "html", "css", "rest", "graphql", "microservices", "api",
}

_RESPONSIBILITY_KEYWORDS: set[str] = {
    "managed", "led", "developed", "designed", "implemented", "maintained",
    "coordinated", "supervised", "directed", "oversaw", "executed",
    "delivered", "architected", "built", "created", "established",
    "mentored", "trained", "collaborated", "facilitated",
}

_ACHIEVEMENT_KEYWORDS: set[str] = {
    "increased", "decreased", "reduced", "improved", "achieved", "awarded",
    "recognized", "promoted", "published", "patented", "launched",
    "exceeded", "surpassed", "generated", "saved", "optimized",
}

_CERTIFICATION_KEYWORDS: set[str] = {
    "certified", "certification", "certificate", "licensed", "accredited",
    "diploma", "credential",
}


# ── Lazy spaCy loader ────────────────────────────────────────────────────────

_nlp: Any = None


def _get_nlp() -> Any:
    """Load spaCy model lazily (once per process)."""
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load(SPACY_MODEL)
    return _nlp


# ── Public API ────────────────────────────────────────────────────────────────


def extract(*, db: Session, resume: ResumeDocument) -> list[CandidateFact]:
    """
    Extract candidate facts from a resume document's text.

    Uses spaCy NER to identify entities and classify them into 6 claim types.
    Augments NER with keyword-based heuristics for resume-specific patterns.

    Every extracted fact gets:
        - verification_status = "Needs Confirmation"
        - original_claim_text = claim_text (immutable after creation)
        - source_span = {start, end} from spaCy token character positions

    Args:
        db: Active database session.
        resume: The ResumeDocument to extract from.

    Returns:
        List of persisted CandidateFact instances.
    """
    nlp = _get_nlp()
    text = resume.extracted_text
    doc = nlp(text)

    facts: list[CandidateFact] = []
    seen_spans: set[tuple[int, int]] = set()

    # ── NER-based extraction ──────────────────────────────────────────────
    for ent in doc.ents:
        claim_type = _LABEL_TO_CLAIM_TYPE.get(ent.label_)
        if claim_type is None:
            continue

        span_key = (ent.start_char, ent.end_char)
        if span_key in seen_spans:
            continue
        seen_spans.add(span_key)

        claim_text = ent.text.strip()
        if not claim_text:
            continue

        fact = CandidateFact(
            candidate_id=resume.candidate_id,
            claim_text=claim_text,
            original_claim_text=claim_text,
            claim_type=claim_type,
            source_document_id=resume.id,
            source_span={"start": ent.start_char, "end": ent.end_char},
            verification_status=VerificationStatus.NEEDS_CONFIRMATION,
            metadata_={},
        )
        facts.append(fact)

    # ── Keyword-based extraction (sentence level) ─────────────────────────
    for sent in doc.sents:
        sent_text = sent.text.strip()
        if not sent_text:
            continue
        sent_lower = sent_text.lower()

        # Skill keywords
        for kw in _SKILL_KEYWORDS:
            if kw in sent_lower:
                span_key = (sent.start_char, sent.end_char)
                if span_key not in seen_spans:
                    seen_spans.add(span_key)
                    fact = CandidateFact(
                        candidate_id=resume.candidate_id,
                        claim_text=sent_text,
                        original_claim_text=sent_text,
                        claim_type=ClaimType.SKILL,
                        source_document_id=resume.id,
                        source_span={"start": sent.start_char, "end": sent.end_char},
                        verification_status=VerificationStatus.NEEDS_CONFIRMATION,
                        metadata_={"keyword": kw},
                    )
                    facts.append(fact)
                break  # one match per sentence is enough

        # Responsibility keywords
        for kw in _RESPONSIBILITY_KEYWORDS:
            if kw in sent_lower:
                span_key = (sent.start_char, sent.end_char)
                if span_key not in seen_spans:
                    seen_spans.add(span_key)
                    fact = CandidateFact(
                        candidate_id=resume.candidate_id,
                        claim_text=sent_text,
                        original_claim_text=sent_text,
                        claim_type=ClaimType.RESPONSIBILITY,
                        source_document_id=resume.id,
                        source_span={"start": sent.start_char, "end": sent.end_char},
                        verification_status=VerificationStatus.NEEDS_CONFIRMATION,
                        metadata_={"keyword": kw},
                    )
                    facts.append(fact)
                break

        # Achievement keywords
        for kw in _ACHIEVEMENT_KEYWORDS:
            if kw in sent_lower:
                span_key = (sent.start_char, sent.end_char)
                if span_key not in seen_spans:
                    seen_spans.add(span_key)
                    fact = CandidateFact(
                        candidate_id=resume.candidate_id,
                        claim_text=sent_text,
                        original_claim_text=sent_text,
                        claim_type=ClaimType.ACHIEVEMENT,
                        source_document_id=resume.id,
                        source_span={"start": sent.start_char, "end": sent.end_char},
                        verification_status=VerificationStatus.NEEDS_CONFIRMATION,
                        metadata_={"keyword": kw},
                    )
                    facts.append(fact)
                break

        # Certification keywords
        for kw in _CERTIFICATION_KEYWORDS:
            if kw in sent_lower:
                span_key = (sent.start_char, sent.end_char)
                if span_key not in seen_spans:
                    seen_spans.add(span_key)
                    fact = CandidateFact(
                        candidate_id=resume.candidate_id,
                        claim_text=sent_text,
                        original_claim_text=sent_text,
                        claim_type=ClaimType.CERTIFICATION,
                        source_document_id=resume.id,
                        source_span={"start": sent.start_char, "end": sent.end_char},
                        verification_status=VerificationStatus.NEEDS_CONFIRMATION,
                        metadata_={"keyword": kw},
                    )
                    facts.append(fact)
                break

    # ── Persist ───────────────────────────────────────────────────────────
    if facts:
        db.add_all(facts)
        db.commit()
        for fact in facts:
            db.refresh(fact)

    return facts
