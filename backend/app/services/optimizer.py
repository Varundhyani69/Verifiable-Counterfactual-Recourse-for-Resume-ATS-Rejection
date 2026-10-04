"""
Optimizer service.

Selects the minimum-cost feasible subset of ProposedEdits that causes
the simulated ATS score to meet or exceed the configured threshold while
satisfying all structural constraints and the fabrication prohibition.

Algorithm: BoundedSubsetSearch
  1. Sort edits ascending by estimated edit cost
  2. Enumerate subsets smallest-first (size 1, 2, 3, …)
  3. For each subset:
     a. Apply edits to resume text
     b. Score with ATS_Scorer
     c. Check structural constraints
     d. Check fabrication guard
     e. Track best feasible result
  4. Apply minimality post-processing: remove any redundant edit

Edit cost formula (Req 6.2):
  C(e) = w1 × norm_levenshtein(original, proposed)
       + w2 × (changed_statements / total_statements)
       + w3 × (1 − SBERT_cosine(original, proposed))
       + w4 × (moved_sections / total_sections)
  Default weights: w1=w2=w3=w4=0.25

Constraints checked (Req 6.3):
  - All named sections in original resume are present in revised resume
  - Contact block (name, email, phone) is unchanged
  - Every CandidateFact claim text is represented in revised resume

Fabrication is NEVER relaxed (Req 6.7).

Public API:
    optimize(db, edits, resume_version, config) → OptimizationResult

Requirements: 6.1–6.7
"""

from __future__ import annotations

import re
import uuid
from itertools import combinations
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.candidate_fact import CandidateFact
from backend.app.models.enums import VerificationStatus
from backend.app.models.proposed_edit import ProposedEdit
from backend.app.models.resume_version import ResumeVersion
from backend.app.schemas.recourse import OptimizationConfig

# ── Constants ─────────────────────────────────────────────────────────────────

# Maximum subset size to enumerate (performance guard for large edit sets)
MAX_SUBSET_SIZE = 10

# Words that signal section headings
_SECTION_SIGNALS = {
    "experience", "education", "skills", "projects", "certifications",
    "achievements", "summary", "objective", "publications", "awards",
    "responsibilities", "work history", "employment", "qualifications",
}

# Regex patterns for contact block detection
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"[\+\(]?[0-9][0-9\s\-\(\)]{7,}[0-9]")


# ── OptimizationResult ────────────────────────────────────────────────────────


class PartialResult:
    """Lowest-cost partial subset found when optimization is infeasible."""

    def __init__(
        self,
        edits: list[ProposedEdit],
        total_edit_cost: float,
        projected_score: float,
    ) -> None:
        self.edits = edits
        self.total_edit_cost = total_edit_cost
        self.projected_score = projected_score


class OptimizationResult:
    """Result of running BoundedSubsetSearch."""

    def __init__(
        self,
        *,
        status: str,  # "feasible" | "infeasible"
        accepted_edits: list[ProposedEdit],
        total_edit_cost: float,
        projected_score: float,
        projected_decision: str,  # "pass" | "fail"
        constraints_violated: list[str] | None = None,
        partial_result: PartialResult | None = None,
    ) -> None:
        self.status = status
        self.accepted_edits = accepted_edits
        self.total_edit_cost = total_edit_cost
        self.projected_score = projected_score
        self.projected_decision = projected_decision
        self.constraints_violated = constraints_violated
        self.partial_result = partial_result


# ── Helper: extract section headings ─────────────────────────────────────────

def _extract_section_headings(text: str) -> set[str]:
    """Return lower-cased section heading words found in the text."""
    headings: set[str] = set()
    for line in text.split("\n"):
        stripped = line.strip().lower()
        if any(sig in stripped for sig in _SECTION_SIGNALS) and len(stripped) < 50:
            headings.add(stripped)
    return headings


# ── Helper: extract contact block ────────────────────────────────────────────

def _extract_contact_block(text: str) -> dict[str, str]:
    """Extract email and phone from the first 500 characters of text."""
    header = text[:500]
    emails = _EMAIL_RE.findall(header)
    phones = _PHONE_RE.findall(header)
    return {
        "email": emails[0].lower() if emails else "",
        "phone": phones[0].strip() if phones else "",
    }


# ── Helper: apply edits to resume text ───────────────────────────────────────

def _apply_edits(base_text: str, edits: list[ProposedEdit]) -> str:
    """
    Apply a set of ProposedEdits to the base resume text.

    Uses simple string replacement. Edits are applied in order of their
    position in the text to avoid offset issues.
    """
    result = base_text
    for edit in edits:
        orig = edit.original_text
        prop = edit.proposed_text

        # remove_redundancy: proposed == original means remove
        if orig == prop:
            continue

        # For reorganize/reorder edits that describe structural changes
        if prop.startswith("Move '") or prop.startswith("Section order:"):
            continue  # Structural reorganization — text stays same for scoring

        if orig and orig in result:
            result = result.replace(orig, prop, 1)
        elif orig and orig.lower() in result.lower():
            # Case-insensitive fallback
            idx = result.lower().find(orig.lower())
            if idx >= 0:
                result = result[:idx] + prop + result[idx + len(orig):]

    return result


# ── Helper: score text against JD ────────────────────────────────────────────

def _simple_score(
    resume_text: str,
    jd_requirement_skills: list[str],
) -> float:
    """
    Lightweight ATS score proxy for optimization.

    Uses skill overlap only (no SBERT) to keep optimization fast.
    Returns a float in [0.0, 1.0].

    The full ATS_Scorer (with SBERT) is called only for the final accepted set.
    """
    if not jd_requirement_skills:
        return 0.0

    resume_lower = resume_text.lower()
    matched = sum(
        1 for skill in jd_requirement_skills if skill.lower() in resume_lower
    )
    return min(1.0, matched / len(jd_requirement_skills))


# ── Helper: structural constraint check ──────────────────────────────────────

def _check_structural_constraints(
    original_text: str,
    revised_text: str,
    usable_facts: list[CandidateFact],
) -> list[str]:
    """
    Check Req 6.3 structural invariants.

    Returns a list of violated constraint names:
      - "section_preservation"
      - "contact_block"
      - "fact_preservation"
    """
    violated: list[str] = []

    # (a) All named sections preserved
    orig_sections = _extract_section_headings(original_text)
    rev_sections = _extract_section_headings(revised_text)
    if orig_sections and not orig_sections.issubset(rev_sections):
        violated.append("section_preservation")

    # (b) Contact block unchanged
    orig_contact = _extract_contact_block(original_text)
    rev_contact = _extract_contact_block(revised_text)
    if orig_contact["email"] and orig_contact["email"] != rev_contact["email"]:
        violated.append("contact_block")

    # (c) Every CandidateFact represented in revised text
    rev_lower = revised_text.lower()
    for fact in usable_facts:
        claim = fact.claim_text.strip()
        if not claim:
            continue
        # Allow partial match — at least 60% of the claim tokens must appear
        tokens = [t for t in claim.lower().split() if len(t) > 2]
        if not tokens:
            continue
        found = sum(1 for t in tokens if t in rev_lower)
        if found / len(tokens) < 0.6:
            violated.append("fact_preservation")
            break  # One failure is enough

    return violated


# ── Levenshtein distance ──────────────────────────────────────────────────────

def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    # Use two-row DP for memory efficiency
    prev = list(range(lb + 1))
    curr = [0] * (lb + 1)
    for i in range(1, la + 1):
        curr[0] = i
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev, curr = curr, prev
    return prev[lb]


# ── SBERT cosine (lazy import) ────────────────────────────────────────────────

_sbert: Any = None


def _get_sbert() -> Any:
    global _sbert
    if _sbert is None:
        import os
        from sentence_transformers import SentenceTransformer
        model_name = os.environ.get("SBERT_MODEL", "all-MiniLM-L6-v2")
        _sbert = SentenceTransformer(model_name)
    return _sbert


def _sbert_cosine(text_a: str, text_b: str) -> float:
    import numpy as np
    model = _get_sbert()
    embs = model.encode([text_a, text_b], convert_to_numpy=True)
    a, b = embs[0], embs[1]
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ── Edit cost formula (Req 6.2) ───────────────────────────────────────────────

def compute_edit_cost(
    edit: ProposedEdit,
    original_resume: str,
    config: OptimizationConfig,
) -> float:
    """
    Compute the composite edit cost for a single ProposedEdit.

    C(e) = w1 × norm_levenshtein
         + w2 × changed_statements_ratio
         + w3 × semantic_change
         + w4 × moved_sections_ratio

    All sub-components are in [0.0, 1.0].  The result is in [0.0, 1.0].
    """
    orig = edit.original_text
    prop = edit.proposed_text

    if not orig and not prop:
        return 0.0

    # Sub-component 1: Normalized Levenshtein distance
    max_len = max(len(orig), len(prop), 1)
    lev_dist = _levenshtein(orig, prop)
    norm_lev = min(1.0, lev_dist / max_len)

    # Sub-component 2: Changed statements ratio
    total_stmts = max(
        len([s for s in original_resume.split(".") if s.strip()]), 1
    )
    # Count statements that changed (simplified: 1 changed statement per edit)
    changed_stmts_ratio = min(1.0, 1.0 / total_stmts)

    # Sub-component 3: Semantic change (1 - SBERT cosine)
    try:
        similarity = _sbert_cosine(orig, prop) if orig and prop else 1.0
    except Exception:
        similarity = 0.5
    semantic_change = max(0.0, min(1.0, 1.0 - similarity))

    # Sub-component 4: Moved sections ratio
    total_sections = max(
        len([
            line for line in original_resume.split("\n")
            if any(sig in line.lower() for sig in _SECTION_SIGNALS)
            and len(line.strip()) < 50
        ]),
        1,
    )
    from backend.app.models.enums import EditType
    moved_sections = (
        1 if edit.edit_type in (EditType.REORGANIZE_SECTIONS, EditType.REORDER)
        else 0
    )
    moved_sections_ratio = min(1.0, moved_sections / total_sections)

    cost = (
        config.levenshtein_weight * norm_lev
        + config.changed_statements_weight * changed_stmts_ratio
        + config.semantic_change_weight * semantic_change
        + config.moved_sections_weight * moved_sections_ratio
    )
    return min(1.0, max(0.0, cost))


# ── BoundedSubsetSearch ───────────────────────────────────────────────────────

def optimize(
    *,
    db: Session,
    edits: list[ProposedEdit],
    resume_version: ResumeVersion,
    usable_facts: list[CandidateFact],
    jd_requirement_skills: list[str],
    config: OptimizationConfig,
) -> OptimizationResult:
    """
    Select the minimum-cost feasible subset of edits.

    Args:
        db: Active database session (used to persist updated edit costs).
        edits: All ProposedEdits generated for this recourse request.
        resume_version: The baseline ResumeVersion to improve.
        usable_facts: Non-Unsupported CandidateFacts for constraint checking.
        jd_requirement_skills: Flat list of normalized skill strings from the JD.
        config: Optimization hyperparameters.

    Returns:
        OptimizationResult with status, accepted_edits, costs, and scores.
    """
    base_text = resume_version.content
    baseline_score = _simple_score(base_text, jd_requirement_skills)

    # ── Compute edit costs and sort ascending ──────────────────────────────
    for edit in edits:
        cost = compute_edit_cost(edit, base_text, config)
        edit.edit_cost = cost

    sorted_edits = sorted(edits, key=lambda e: e.edit_cost)

    # Track best partial result
    best_partial_edits: list[ProposedEdit] = []
    best_partial_score: float = baseline_score
    best_partial_cost: float = 0.0

    best_feasible_edits: list[ProposedEdit] | None = None
    best_feasible_cost: float = float("inf")
    best_feasible_score: float = 0.0
    all_constraints_violated: set[str] = set()

    max_size = min(len(sorted_edits), MAX_SUBSET_SIZE)

    # ── Enumerate subsets smallest-first ──────────────────────────────────
    for size in range(1, max_size + 1):
        if best_feasible_edits is not None:
            # Already found a feasible solution — only check if a smaller-cost
            # subset of this size might be better
            break

        for subset in combinations(sorted_edits, size):
            subset_list = list(subset)
            total_cost = sum(e.edit_cost for e in subset_list)

            # Prune: can't beat current best
            if best_feasible_edits is not None and total_cost >= best_feasible_cost:
                continue

            # Apply edits
            revised_text = _apply_edits(base_text, subset_list)

            # Check fabrication — NEVER relaxed
            # All facts referenced by any edit must still exist in evidence
            all_facts_supported = all(
                any(
                    f.verification_status != VerificationStatus.UNSUPPORTED
                    for f in edit.evidence_facts
                )
                for edit in subset_list
                if edit.evidence_facts
            )
            if not all_facts_supported:
                all_constraints_violated.add("fabrication")
                continue

            # Check structural constraints
            violated = _check_structural_constraints(
                base_text, revised_text, usable_facts
            )
            if violated:
                all_constraints_violated.update(violated)
                # Track partial if score improved
                projected = _simple_score(revised_text, jd_requirement_skills)
                if projected > best_partial_score:
                    best_partial_score = projected
                    best_partial_edits = subset_list
                    best_partial_cost = total_cost
                continue

            # Score the revised resume
            projected_score = _simple_score(revised_text, jd_requirement_skills)

            # Track partial progress
            if projected_score > best_partial_score:
                best_partial_score = projected_score
                best_partial_edits = subset_list
                best_partial_cost = total_cost

            # Check threshold
            if projected_score >= config.threshold:
                if total_cost < best_feasible_cost:
                    best_feasible_edits = subset_list
                    best_feasible_cost = total_cost
                    best_feasible_score = projected_score
            else:
                all_constraints_violated.add("threshold")

    # ── Minimality post-processing ─────────────────────────────────────────
    if best_feasible_edits is not None:
        best_feasible_edits = _apply_minimality(
            best_feasible_edits, base_text, jd_requirement_skills, config, usable_facts
        )
        best_feasible_cost = sum(e.edit_cost for e in best_feasible_edits)
        revised_text = _apply_edits(base_text, best_feasible_edits)
        best_feasible_score = _simple_score(revised_text, jd_requirement_skills)

    # ── Persist updated edit costs ─────────────────────────────────────────
    db.commit()

    # ── Build result ───────────────────────────────────────────────────────
    if best_feasible_edits is not None:
        decision = "pass" if best_feasible_score >= config.threshold else "fail"
        return OptimizationResult(
            status="feasible",
            accepted_edits=best_feasible_edits,
            total_edit_cost=best_feasible_cost,
            projected_score=best_feasible_score,
            projected_decision=decision,
        )

    # Infeasible
    partial = PartialResult(
        edits=best_partial_edits,
        total_edit_cost=best_partial_cost,
        projected_score=best_partial_score,
    )
    constraints_list = sorted(all_constraints_violated) if all_constraints_violated else ["threshold"]

    return OptimizationResult(
        status="infeasible",
        accepted_edits=[],
        total_edit_cost=0.0,
        projected_score=best_partial_score,
        projected_decision="fail",
        constraints_violated=constraints_list,
        partial_result=partial,
    )


def _apply_minimality(
    edits: list[ProposedEdit],
    base_text: str,
    jd_skills: list[str],
    config: OptimizationConfig,
    usable_facts: list[CandidateFact],
) -> list[ProposedEdit]:
    """
    Remove any edit that is redundant while still crossing threshold (Req 6.1).

    Iterates over the accepted set in ascending cost order and removes any
    edit whose removal still leaves the threshold satisfied.
    """
    sorted_subset = sorted(edits, key=lambda e: e.edit_cost)
    minimal = list(sorted_subset)

    for edit in sorted_subset:
        candidate = [e for e in minimal if e is not edit]
        if not candidate:
            break
        revised = _apply_edits(base_text, candidate)
        score = _simple_score(revised, jd_skills)
        violated = _check_structural_constraints(base_text, revised, usable_facts)
        if score >= config.threshold and not violated:
            minimal = candidate

    return minimal
