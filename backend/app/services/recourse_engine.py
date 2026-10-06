"""
Recourse engine service.

Generates ProposedEdits grounded in the candidate's Evidence Bank,
subject to the six permitted edit types, the rephrase similarity floor,
and the fabrication prohibition.

Each edit must:
  - Use exactly one of the 6 edit types
  - Be grounded in at least one non-Unsupported CandidateFact
  - Address at least one JobRequirement
  - Not introduce any named entity absent from the Evidence Bank
  - Preserve semantic meaning for rephrase edits (SBERT cosine ≥ 0.85)

Public API:
    generate(db, resume_version_id, jd_id, config) → tuple[list[ProposedEdit], str, str | None]

Returns:
    (edits, status, infeasible_reason)
    status ∈ {"ok", "infeasible"}
    infeasible_reason ∈ {None, "no_evidence", "all_unsupported", "no_requirement_match"}

Requirements: 5.1–5.8
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.exceptions import ResourceNotFoundError
from backend.app.models.candidate_fact import CandidateFact
from backend.app.models.enums import (
    ClaimType,
    EditType,
    ImportanceLevel,
    VerificationStatus,
)
from backend.app.models.job_description import JobDescription
from backend.app.models.job_requirement import JobRequirement
from backend.app.models.proposed_edit import ProposedEdit
from backend.app.models.resume_version import ResumeVersion

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_EDITS = 20
REPHRASE_SIMILARITY_FLOOR = 0.85

# Skill canonicalization map (mirrors JD analyzer)
_SKILL_CANON: dict[str, str] = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "py": "Python",
    "python": "Python",
    "ml": "Machine Learning",
    "dl": "Deep Learning",
    "nlp": "Natural Language Processing",
    "k8s": "Kubernetes",
    "kube": "Kubernetes",
    "aws": "AWS",
    "gcp": "Google Cloud Platform",
    "azure": "Microsoft Azure",
    "ci/cd": "CI/CD",
    "css": "CSS",
    "html": "HTML",
    "sql": "SQL",
    "nosql": "NoSQL",
    "rest": "REST",
    "api": "API",
    "oop": "Object-Oriented Programming",
    "react": "React",
    "vue": "Vue.js",
    "angular": "Angular",
    "node": "Node.js",
    "nodejs": "Node.js",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "spring": "Spring",
    "docker": "Docker",
    "git": "Git",
    "linux": "Linux",
    "agile": "Agile",
    "scrum": "Scrum",
}

# Redundancy phrases — pairs where one phrasing dominates another
_REDUNDANT_PATTERNS: list[tuple[str, str]] = [
    ("developed and implemented", "implemented"),
    ("built and developed", "developed"),
    ("created and designed", "designed"),
    ("managed and led", "led"),
    ("assisted and supported", "supported"),
    ("designed and architected", "architected"),
]

# Words that signal sections in a resume
_SECTION_SIGNALS = {
    "experience", "education", "skills", "projects", "certifications",
    "achievements", "summary", "objective", "publications", "awards",
    "responsibilities", "work history", "employment", "qualifications",
}


# ── spaCy lazy loader ─────────────────────────────────────────────────────────

_nlp: Any = None


def _get_nlp() -> Any:
    """Load spaCy model lazily."""
    global _nlp
    if _nlp is None:
        import os
        import spacy
        model = os.environ.get("SPACY_MODEL", "en_core_web_sm")
        _nlp = spacy.load(model)
    return _nlp


# ── SBERT lazy loader ────────────────────────────────────────────────────────

_sbert: Any = None


def _get_sbert() -> Any:
    """Load Sentence-BERT model lazily."""
    global _sbert
    if _sbert is None:
        import os
        from sentence_transformers import SentenceTransformer
        model_name = os.environ.get("SBERT_MODEL", "all-MiniLM-L6-v2")
        _sbert = SentenceTransformer(model_name)
    return _sbert


# ── Helper: extract named entities from text ─────────────────────────────────

def _extract_entities(text: str) -> set[str]:
    """Return the set of named entity strings found in ``text`` via spaCy NER."""
    nlp = _get_nlp()
    doc = nlp(text)
    return {ent.text.lower().strip() for ent in doc.ents}


def _build_evidence_entity_set(facts: list[CandidateFact]) -> set[str]:
    """Collect all entity strings across all CandidateFact claim texts."""
    entities: set[str] = set()
    for fact in facts:
        entities.update(_extract_entities(fact.claim_text))
    return entities


# ── Helper: compute SBERT cosine similarity ──────────────────────────────────

def _sbert_cosine(text_a: str, text_b: str) -> float:
    """
    Compute cosine similarity between two texts using Sentence-BERT.

    Returns a float in [0.0, 1.0].  A score ≥ 0.85 satisfies the rephrase
    semantic preservation requirement (Req 5.4).
    """
    import numpy as np
    model = _get_sbert()
    embs = model.encode([text_a, text_b], convert_to_numpy=True)
    a, b = embs[0], embs[1]
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ── Fabrication guard ─────────────────────────────────────────────────────────

def _passes_fabrication_guard(
    proposed_text: str,
    evidence_entity_set: set[str],
) -> bool:
    """
    Return True if every named entity in ``proposed_text`` exists in the
    Evidence Bank entity set.

    An edit that introduces a new entity not present in any CandidateFact
    violates the fabrication prohibition (Req 5.3, 6.7).
    """
    proposed_entities = _extract_entities(proposed_text)
    new_entities = proposed_entities - evidence_entity_set
    return len(new_entities) == 0


# ── Skill extraction helper ──────────────────────────────────────────────────

def _extract_skill_tokens(text: str) -> set[str]:
    """Return lower-cased word tokens from text for skill overlap checks."""
    return {w.lower().strip(".,;:()") for w in text.split() if len(w) > 1}


# ── Edit type handlers ────────────────────────────────────────────────────────

def _generate_normalize_terminology_edits(
    resume_text: str,
    usable_facts: list[CandidateFact],
    requirements: list[JobRequirement],
    evidence_entity_set: set[str],
) -> list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]]:
    """
    Generate normalize_terminology edits.

    Finds skill mentions in the resume that have a canonical form in the
    JD normalization map and proposes replacing them with the canonical name.

    Returns list of (original_text, proposed_text, fact_ids, req_ids, score_contribution).
    """
    results: list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]] = []
    resume_lower = resume_text.lower()

    for alias, canonical in _SKILL_CANON.items():
        if alias == canonical.lower():
            continue  # Already canonical

        # Check if this alias appears in resume text
        pattern = r"\b" + re.escape(alias) + r"\b"
        matches = list(re.finditer(pattern, resume_lower, re.IGNORECASE))
        if not matches:
            continue

        # Find requirements that mention this canonical skill
        matching_reqs: list[uuid.UUID] = []
        for req in requirements:
            req_skills_lower = {s.lower() for s in req.normalized_skills}
            if canonical.lower() in req_skills_lower or alias in req_skills_lower:
                matching_reqs.append(req.id)

        if not matching_reqs:
            continue

        # Find facts that support this skill
        supporting_facts: list[uuid.UUID] = []
        for fact in usable_facts:
            if alias in fact.claim_text.lower() or canonical.lower() in fact.claim_text.lower():
                supporting_facts.append(fact.id)

        if not supporting_facts:
            continue

        # Extract the actual substring from resume
        match = matches[0]
        original = resume_text[match.start():match.end()]
        proposed = canonical

        if not _passes_fabrication_guard(proposed, evidence_entity_set):
            continue

        results.append((original, proposed, supporting_facts, matching_reqs, 0.04))

    return results


def _generate_rephrase_edits(
    usable_facts: list[CandidateFact],
    requirements: list[JobRequirement],
    evidence_entity_set: set[str],
) -> list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]]:
    """
    Generate rephrase edits.

    Proposes adding context from a CandidateFact to match a JobRequirement
    more clearly. The proposed text adds requirement-relevant phrasing to the
    original claim, verified to remain ≥ 0.85 cosine similarity.
    """
    results: list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]] = []
    seen_originals: set[str] = set()

    for req in requirements:
        req_skills_lower = {s.lower() for s in req.normalized_skills}
        req_text_lower = req.requirement_text.lower()

        for fact in usable_facts:
            if fact.claim_type not in (
                ClaimType.SKILL, ClaimType.RESPONSIBILITY, ClaimType.EXPERIENCE
            ):
                continue

            claim_lower = fact.claim_text.lower()
            # Check if fact is relevant to this requirement
            fact_tokens = _extract_skill_tokens(fact.claim_text)
            req_tokens = _extract_skill_tokens(req.requirement_text)
            overlap = fact_tokens & req_tokens & req_skills_lower

            if not overlap and not any(s in claim_lower for s in req_skills_lower):
                # Try broader relevance check
                shared = fact_tokens & req_tokens
                if len(shared) < 2:
                    continue

            original = fact.claim_text
            if original in seen_originals:
                continue

            # Build a clarified rephrase that makes the skill explicit
            # while preserving meaning
            if req.normalized_skills:
                skill = req.normalized_skills[0]
                # Only rephrase if the skill isn't already prominent
                if skill.lower() not in claim_lower:
                    proposed = f"{original} (utilizing {skill})"
                else:
                    # Already mentions the skill — make it more action-oriented
                    proposed = original.replace(
                        original[:20], original[:20]
                    )  # no-op placeholder; skip
                    continue
            else:
                continue

            if not _passes_fabrication_guard(proposed, evidence_entity_set):
                continue

            # Validate similarity floor
            try:
                sim = _sbert_cosine(original, proposed)
            except Exception:
                continue

            if sim < REPHRASE_SIMILARITY_FLOOR:
                continue

            seen_originals.add(original)
            results.append(
                (original, proposed, [fact.id], [req.id], 0.05)
            )

    return results


def _generate_surface_qualification_edits(
    resume_text: str,
    usable_facts: list[CandidateFact],
    requirements: list[JobRequirement],
    evidence_entity_set: set[str],
) -> list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]]:
    """
    Generate surface_qualification edits.

    Identifies CandidateFacts that match a JobRequirement but whose claim
    text is buried (appears late or in a non-prominent section). Proposes
    surfacing the claim to the top of its section.
    """
    results: list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]] = []
    text_lower = resume_text.lower()
    total_len = max(len(resume_text), 1)

    for fact in usable_facts:
        if fact.claim_type not in (ClaimType.SKILL, ClaimType.CERTIFICATION, ClaimType.ACHIEVEMENT):
            continue

        claim = fact.claim_text
        pos = fact.source_span.get("start", 0) if fact.source_span else 0
        relative_pos = pos / total_len

        # Only surface facts that appear in the latter half of the document
        if relative_pos < 0.5:
            continue

        # Find matching requirements
        claim_lower = claim.lower()
        matching_reqs: list[uuid.UUID] = []
        for req in requirements:
            req_skills = {s.lower() for s in req.normalized_skills}
            if any(s in claim_lower for s in req_skills):
                matching_reqs.append(req.id)
            elif any(token in claim_lower for token in _extract_skill_tokens(req.requirement_text)):
                matching_reqs.append(req.id)

        if not matching_reqs:
            continue

        # Proposed: surface the claim at the beginning of the skills section
        proposed = f"[Highlighted] {claim}"
        if not _passes_fabrication_guard(proposed, evidence_entity_set):
            continue

        results.append(
            (claim, proposed, [fact.id], matching_reqs[:3], 0.06)
        )

    return results


def _generate_reorder_edits(
    resume_text: str,
    usable_facts: list[CandidateFact],
    requirements: list[JobRequirement],
    evidence_entity_set: set[str],
) -> list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]]:
    """
    Generate reorder edits.

    Proposes reordering bullet points within a section to put the most
    requirement-relevant bullet first.
    """
    results: list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]] = []
    lines = resume_text.split("\n")
    if len(lines) < 3:
        return results

    # Find bullet groups (lines starting with - or •)
    bullet_groups: list[tuple[int, int]] = []
    in_group = False
    group_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("-", "•", "*")):
            if not in_group:
                in_group = True
                group_start = i
        else:
            if in_group:
                bullet_groups.append((group_start, i))
                in_group = False
    if in_group:
        bullet_groups.append((group_start, len(lines)))

    for g_start, g_end in bullet_groups:
        bullets = lines[g_start:g_end]
        if len(bullets) < 2:
            continue

        # Score each bullet against requirements
        scored: list[tuple[int, float, uuid.UUID | None]] = []
        for idx, bullet in enumerate(bullets):
            b_lower = bullet.lower()
            score = 0.0
            best_req_id: uuid.UUID | None = None
            for req in requirements:
                req_skills = {s.lower() for s in req.normalized_skills}
                matches = sum(1 for s in req_skills if s in b_lower)
                if matches > score:
                    score = float(matches)
                    best_req_id = req.id
            scored.append((idx, score, best_req_id))

        # Check if first bullet is NOT the highest-scoring one
        scored.sort(key=lambda x: -x[1])
        best_idx, best_score, best_req_id = scored[0]

        if best_idx == 0 or best_score == 0 or best_req_id is None:
            continue

        original_block = "\n".join(bullets)
        # Reordered: best bullet first, then rest in original order
        reordered = [bullets[best_idx]] + [
            b for j, b in enumerate(bullets) if j != best_idx
        ]
        proposed_block = "\n".join(reordered)

        if original_block == proposed_block:
            continue

        # Find supporting fact
        best_bullet_lower = bullets[best_idx].lower()
        supporting_facts = [
            f.id for f in usable_facts
            if any(tok in best_bullet_lower for tok in _extract_skill_tokens(f.claim_text))
        ][:2]

        if not supporting_facts:
            continue

        if not _passes_fabrication_guard(proposed_block, evidence_entity_set):
            continue

        results.append(
            (original_block, proposed_block, supporting_facts, [best_req_id], 0.03)
        )

    return results


def _generate_reorganize_sections_edits(
    resume_text: str,
    usable_facts: list[CandidateFact],
    requirements: list[JobRequirement],
    evidence_entity_set: set[str],
) -> list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]]:
    """
    Generate reorganize_sections edits.

    Identifies a section that is highly relevant to the JD but appears late
    in the document and proposes moving it higher.
    """
    results: list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]] = []
    lines = resume_text.split("\n")

    # Identify section headings
    sections: list[tuple[str, int]] = []  # (heading, line_index)
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if any(sig in stripped for sig in _SECTION_SIGNALS) and len(stripped) < 40:
            sections.append((line.strip(), i))

    if len(sections) < 2:
        return results

    # Score each section against requirements
    req_skills_all = {s.lower() for req in requirements for s in req.normalized_skills}
    req_types = {req.requirement_type.value for req in requirements}

    scored_sections: list[tuple[str, int, float]] = []
    for heading, line_idx in sections:
        heading_lower = heading.lower()
        score = sum(1.0 for sig in req_skills_all if sig in heading_lower)
        # Skills section is almost always relevant
        if "skill" in heading_lower:
            score += 2.0
        if any(rt in heading_lower for rt in req_types):
            score += 1.0
        scored_sections.append((heading, line_idx, score))

    scored_sections.sort(key=lambda x: -x[2])
    if not scored_sections:
        return results

    best_heading, best_line, best_score = scored_sections[0]
    if best_score == 0:
        return results

    # Only propose if it's not already the first section
    first_section_line = sections[0][1]
    if best_line == first_section_line:
        return results

    # Find matching requirements
    matching_reqs = [
        req.id for req in requirements
        if "skill" in req.requirement_type.value or
        any(s.lower() in best_heading.lower() for s in req.normalized_skills)
    ][:3]

    if not matching_reqs:
        matching_reqs = [requirements[0].id] if requirements else []

    if not matching_reqs:
        return results

    # Supporting facts from the relevant section
    supporting_facts = [
        f.id for f in usable_facts
        if f.claim_type == ClaimType.SKILL
    ][:2]

    if not supporting_facts:
        return results

    original_text = f"Section order: {', '.join(h for h, _ in sections)}"
    proposed_text = f"Move '{best_heading}' before '{sections[0][0]}'"

    if not _passes_fabrication_guard(proposed_text, evidence_entity_set):
        return results

    results.append(
        (original_text, proposed_text, supporting_facts, matching_reqs, 0.04)
    )
    return results


def _generate_remove_redundancy_edits(
    resume_text: str,
    usable_facts: list[CandidateFact],
    requirements: list[JobRequirement],
    evidence_entity_set: set[str],
) -> list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]]:
    """
    Generate remove_redundancy edits.

    Detects sentences that repeat substantially the same content as another
    sentence in the same section and proposes removing the redundant one.
    """
    results: list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]] = []
    sentences = [s.strip() for s in re.split(r"[.!?\n]", resume_text) if len(s.strip()) > 10]

    seen_sents: set[str] = set()
    for i, sent in enumerate(sentences):
        sent_lower = sent.lower()

        # Check for explicit redundant pattern
        for long_form, short_form in _REDUNDANT_PATTERNS:
            if long_form in sent_lower:
                proposed = sent_lower.replace(long_form, short_form)
                # Title-case restore
                proposed = sent[:len(sent) - len(sent.lstrip())] + proposed.lstrip()

                matching_reqs = [req.id for req in requirements][:2]
                supporting_facts = [
                    f.id for f in usable_facts
                    if any(tok in sent_lower for tok in _extract_skill_tokens(f.claim_text))
                ][:2]

                if not supporting_facts or not matching_reqs:
                    continue
                if not _passes_fabrication_guard(proposed, evidence_entity_set):
                    continue

                results.append((sent, proposed, supporting_facts, matching_reqs, 0.02))
                break

        # Check for near-duplicate sentences
        tokens_i = _extract_skill_tokens(sent)
        for prev_sent in seen_sents:
            tokens_prev = _extract_skill_tokens(prev_sent)
            if not tokens_i or not tokens_prev:
                continue
            overlap = len(tokens_i & tokens_prev) / max(len(tokens_i), len(tokens_prev))
            if overlap > 0.75 and sent != prev_sent:
                # Remove the shorter / later duplicate
                to_remove = sent if len(sent) <= len(prev_sent) else prev_sent
                matching_reqs = [req.id for req in requirements][:2]
                supporting_facts = [
                    f.id for f in usable_facts
                    if any(tok in to_remove.lower() for tok in _extract_skill_tokens(f.claim_text))
                ][:2]
                if not supporting_facts or not matching_reqs:
                    continue
                if not _passes_fabrication_guard("", evidence_entity_set):
                    continue
                results.append((to_remove, "", supporting_facts, matching_reqs, 0.02))
                break

        seen_sents.add(sent)

    return results


# ── Score contribution estimator ─────────────────────────────────────────────

def _estimate_score_contribution(
    original_text: str,
    proposed_text: str,
    requirements: list[JobRequirement],
    req_ids: list[uuid.UUID],
) -> float:
    """
    Estimate the ATS score delta from applying a single edit.

    Uses skill overlap improvement as a proxy: counts how many requirement
    skills are newly covered by the proposed text vs the original.
    """
    if not proposed_text:
        return 0.01  # remove_redundancy has small positive contribution

    addressed_reqs = [r for r in requirements if r.id in req_ids]
    if not addressed_reqs:
        return 0.01

    total_skills = sum(len(r.normalized_skills) for r in addressed_reqs)
    if total_skills == 0:
        return 0.01

    orig_lower = original_text.lower()
    prop_lower = proposed_text.lower()

    newly_covered = 0
    for req in addressed_reqs:
        for skill in req.normalized_skills:
            skill_l = skill.lower()
            if skill_l not in orig_lower and skill_l in prop_lower:
                newly_covered += 1

    return min(0.15, newly_covered / total_skills * 0.15)


# ── Public API ────────────────────────────────────────────────────────────────


def generate(
    *,
    db: Session,
    resume_version_id: uuid.UUID,
    job_description_id: uuid.UUID,
) -> tuple[list[ProposedEdit], str, str | None, str | None]:
    """
    Generate ProposedEdits for a resume version against a job description.

    Args:
        db: Active database session.
        resume_version_id: The resume version to generate edits for.
        job_description_id: The target job description.

    Returns:
        (edits, status, infeasible_reason, infeasible_detail)
        status ∈ {"ok", "infeasible"}
        infeasible_reason ∈ {None, "no_evidence", "all_unsupported", "no_requirement_match"}

    Raises:
        ResourceNotFoundError: resume_version_id or job_description_id not found.
    """
    # ── Load domain objects ───────────────────────────────────────────────
    resume_version = db.get(ResumeVersion, resume_version_id)
    if resume_version is None:
        raise ResourceNotFoundError("ResumeVersion", str(resume_version_id))

    jd = db.get(JobDescription, job_description_id)
    if jd is None:
        raise ResourceNotFoundError("JobDescription", str(job_description_id))

    # ── Load usable facts (non-Unsupported) ───────────────────────────────
    candidate_id = resume_version.original_resume.candidate_id
    all_facts: list[CandidateFact] = list(
        db.execute(
            select(CandidateFact).where(
                CandidateFact.candidate_id == candidate_id
            )
        ).scalars().all()
    )

    if not all_facts:
        return [], "infeasible", "no_evidence", (
            "No CandidateFacts found for this resume. "
            "Please ensure the resume was ingested and evidence was extracted."
        )

    usable_facts = [
        f for f in all_facts
        if f.verification_status != VerificationStatus.UNSUPPORTED
    ]

    if not usable_facts:
        return [], "infeasible", "all_unsupported", (
            "All CandidateFacts have verification_status='Unsupported'. "
            "No usable evidence remains for generating edits."
        )

    # ── Load job requirements ──────────────────────────────────────────────
    requirements: list[JobRequirement] = list(
        db.execute(
            select(JobRequirement).where(
                JobRequirement.job_description_id == job_description_id
            )
        ).scalars().all()
    )

    if not requirements:
        return [], "infeasible", "no_requirement_match", (
            "No JobRequirements found for this job description. "
            "Please ensure the job description was analyzed before generating recourse."
        )

    resume_text = resume_version.content
    evidence_entity_set = _build_evidence_entity_set(usable_facts)

    # ── Generate edit candidates ───────────────────────────────────────────
    # (original_text, proposed_text, fact_ids, req_ids, score_contribution)
    raw_candidates: list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]] = []

    # 1. normalize_terminology — highest value, lowest cost
    raw_candidates.extend(
        _generate_normalize_terminology_edits(
            resume_text, usable_facts, requirements, evidence_entity_set
        )
    )

    # 2. surface_qualification
    raw_candidates.extend(
        _generate_surface_qualification_edits(
            resume_text, usable_facts, requirements, evidence_entity_set
        )
    )

    # 3. reorder
    raw_candidates.extend(
        _generate_reorder_edits(
            resume_text, usable_facts, requirements, evidence_entity_set
        )
    )

    # 4. reorganize_sections
    raw_candidates.extend(
        _generate_reorganize_sections_edits(
            resume_text, usable_facts, requirements, evidence_entity_set
        )
    )

    # 5. remove_redundancy
    raw_candidates.extend(
        _generate_remove_redundancy_edits(
            resume_text, usable_facts, requirements, evidence_entity_set
        )
    )

    # 6. rephrase — most expensive, try last so we don't exceed cap
    raw_candidates.extend(
        _generate_rephrase_edits(
            usable_facts, requirements, evidence_entity_set
        )
    )

    if not raw_candidates:
        return [], "infeasible", "no_requirement_match", (
            "No edits could be generated that satisfy all constraints "
            "(grounding, fabrication prohibition, requirement linkage)."
        )

    # ── Deduplicate and cap ────────────────────────────────────────────────
    seen: set[tuple[str, str]] = set()
    unique_candidates: list[tuple[str, str, list[uuid.UUID], list[uuid.UUID], float]] = []
    for orig, prop, fids, rids, sc in raw_candidates:
        key = (orig, prop)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append((orig, prop, fids, rids, sc))

    # Cap at MAX_EDITS
    unique_candidates = unique_candidates[:MAX_EDITS]

    # ── Determine edit types ───────────────────────────────────────────────
    def _infer_edit_type(
        original: str, proposed: str
    ) -> EditType:
        """Classify an edit into one of the 6 permitted types."""
        if not proposed:
            return EditType.REMOVE_REDUNDANCY
        if proposed.startswith("[Highlighted]"):
            return EditType.SURFACE_QUALIFICATION
        if proposed.startswith("Move '"):
            return EditType.REORGANIZE_SECTIONS
        if proposed.startswith("Section order:"):
            return EditType.REORGANIZE_SECTIONS
        if "\n" in original and "\n" in proposed:
            return EditType.REORDER
        # Check if original term maps to canonical
        orig_lower = original.lower()
        for alias, canonical in _SKILL_CANON.items():
            if orig_lower == alias and proposed == canonical:
                return EditType.NORMALIZE_TERMINOLOGY
        # Default to rephrase
        return EditType.REPHRASE

    # ── Persist ProposedEdits ──────────────────────────────────────────────
    persisted_edits: list[ProposedEdit] = []

    for orig, prop, fact_ids, req_ids, sc in unique_candidates:
        edit_type = _infer_edit_type(orig, prop)

        # Re-validate: all referenced facts must still be non-Unsupported
        valid_fact_ids = [
            fid for fid in fact_ids
            if any(
                f.id == fid and f.verification_status != VerificationStatus.UNSUPPORTED
                for f in usable_facts
            )
        ]
        if not valid_fact_ids:
            continue

        # Load ORM objects for relationships
        facts_objs = [f for f in usable_facts if f.id in valid_fact_ids]
        req_objs = [r for r in requirements if r.id in req_ids]

        if not req_objs:
            continue

        score_contribution = _estimate_score_contribution(orig, prop, requirements, req_ids)

        edit = ProposedEdit(
            resume_version_id=resume_version_id,
            original_text=orig,
            proposed_text=prop if prop else orig,  # remove_redundancy: keep original for display
            edit_type=edit_type,
            edit_cost=0.0,  # Optimizer fills this
            score_contribution=score_contribution,
        )
        edit.evidence_facts = facts_objs
        edit.job_requirements = req_objs

        db.add(edit)
        persisted_edits.append(edit)

    if not persisted_edits:
        return [], "infeasible", "no_requirement_match", (
            "No edits passed all constraints after deduplication and validation."
        )

    db.commit()
    for edit in persisted_edits:
        db.refresh(edit)

    return persisted_edits, "ok", None, None
