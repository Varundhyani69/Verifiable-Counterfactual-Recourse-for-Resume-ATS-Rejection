"""
ATS Scorer service.

Produces a deterministic, configurable [0.0, 1.0] score from a resume
text + job description text pair using two components:
  1. Skill overlap  — Jaccard similarity of extracted skill token sets
  2. Semantic similarity — cosine similarity of Sentence-BERT embeddings

The SBERT model is loaded once at import time (lazy) and reused for every
request so results are deterministic given identical inputs.

Public API:
    score(resume_text, jd_text, config) → ScoreResult

Requirements: 4.1–4.9
"""

from __future__ import annotations

import os
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# ── ATS disclosure string (Req 4.9) ──────────────────────────────────────────

DISCLOSURE = (
    "This score is produced by a simulated model and does not predict any "
    "employer's hiring decision."
)

# ── Lazy SBERT loader ─────────────────────────────────────────────────────────

_sbert_model: Any = None
_sbert_model_name: str = ""


def _get_sbert(model_name: str) -> Any:
    """
    Load the SBERT model once and reuse it.

    Reloads if the requested model name differs from the cached one.
    Raises RuntimeError (→ 502) when the model cannot be loaded.
    """
    global _sbert_model, _sbert_model_name
    if _sbert_model is None or _sbert_model_name != model_name:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
            _sbert_model = SentenceTransformer(model_name)
            _sbert_model_name = model_name
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                f"Failed to load SBERT model '{model_name}': {exc}"
            ) from exc
    return _sbert_model


# ── Pydantic data models ──────────────────────────────────────────────────────


class ScoringConfig(BaseModel):
    """
    Configurable weights and threshold for the ATS scorer.

    skill_overlap_weight + sbert_weight must equal 1.0 (±1e-9).
    threshold must be in [0.0, 1.0].
    """

    skill_overlap_weight: float = Field(0.5, ge=0.0, le=1.0)
    sbert_weight: float = Field(0.5, ge=0.0, le=1.0)
    threshold: float = Field(0.5, ge=0.0, le=1.0)
    sbert_model_name: str = Field("all-MiniLM-L6-v2")

    @model_validator(mode="after")
    def weights_must_sum_to_one(self) -> "ScoringConfig":
        total = self.skill_overlap_weight + self.sbert_weight
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"skill_overlap_weight + sbert_weight must equal 1.0; got {total:.9f}."
            )
        return self


class ScoreResult(BaseModel):
    """
    Full scoring output returned by the ATS scorer.

    decision is "pass" iff total_score >= threshold.
    """

    total_score: float
    skill_overlap_score: float
    semantic_similarity_score: float
    weights: dict[str, float]
    threshold: float
    decision: Literal["pass", "fail"]
    disclosure: str = DISCLOSURE


# ── Skill extraction ─────────────────────────────────────────────────────────


def _extract_skill_tokens(text: str) -> set[str]:
    """
    Return a set of normalised, lower-cased word tokens from *text*.

    Used for Jaccard skill-overlap scoring.  Filters out very short tokens
    (len < 2) and common stopwords that are not skill names.
    """
    _STOPWORDS = {
        "and", "or", "the", "a", "an", "in", "of", "to", "for", "with",
        "on", "at", "by", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "should", "could", "may", "might", "must", "shall",
        "not", "no", "nor", "but", "yet", "so", "if", "as", "than",
        "that", "this", "it", "its", "we", "you", "they", "their",
        "our", "my", "your", "i", "he", "she", "from", "up", "about",
        "into", "through", "during", "experience", "years", "year",
        "knowledge", "understanding", "ability", "skills", "skill",
        "work", "working", "strong", "good", "excellent", "proficiency",
    }
    tokens: set[str] = set()
    for raw in re.split(r"[\s,;:()\[\]/{}\-+]", text):
        token = raw.strip(".,;:()\"'").lower()
        if len(token) >= 2 and token not in _STOPWORDS:
            tokens.add(token)
    return tokens


# ── Scoring sub-components ────────────────────────────────────────────────────


def _skill_overlap(resume_text: str, jd_text: str) -> float:
    """
    Jaccard similarity between resume and JD skill token sets.

    |intersection| / |union|  →  [0.0, 1.0]
    Returns 0.0 when both sets are empty.
    """
    resume_skills = _extract_skill_tokens(resume_text)
    jd_skills = _extract_skill_tokens(jd_text)
    union = resume_skills | jd_skills
    if not union:
        return 0.0
    intersection = resume_skills & jd_skills
    return len(intersection) / len(union)


def _semantic_similarity(
    resume_text: str,
    jd_text: str,
    model_name: str,
) -> float:
    """
    Cosine similarity between SBERT embeddings of resume and JD texts.

    Returns a value in [0.0, 1.0].
    Raises RuntimeError if the model fails to produce an embedding.
    """
    import numpy as np  # type: ignore[import]

    model = _get_sbert(model_name)
    try:
        embeddings = model.encode(
            [resume_text, jd_text],
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            f"SBERT model failed to produce an embedding: {exc}"
        ) from exc

    vec_a: Any = embeddings[0]
    vec_b: Any = embeddings[1]
    norm_a = float(np.linalg.norm(vec_a))
    norm_b = float(np.linalg.norm(vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    cosine = float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
    # Clamp to [0.0, 1.0] — cosine can be slightly negative for orthogonal texts
    return max(0.0, min(1.0, cosine))


# ── Public API ────────────────────────────────────────────────────────────────


def score(
    resume_text: str,
    jd_text: str,
    config: ScoringConfig,
) -> ScoreResult:
    """
    Compute a weighted ATS score for a resume against a job description.

    Args:
        resume_text: Full text of the resume (any version).
        jd_text:     Full text of the job description.
        config:      ScoringConfig with weights, threshold, and model name.

    Returns:
        ScoreResult with total_score, sub-scores, decision, and disclosure.

    Raises:
        RuntimeError: When the SBERT model fails to produce an embedding
                      (caller should convert to HTTP 502).

    Requirements: 4.1–4.9
    """
    overlap = _skill_overlap(resume_text, jd_text)
    semantic = _semantic_similarity(resume_text, jd_text, config.sbert_model_name)

    total = (
        config.skill_overlap_weight * overlap
        + config.sbert_weight * semantic
    )
    # Clamp to [0.0, 1.0] (floating-point safety)
    total = max(0.0, min(1.0, total))

    decision: Literal["pass", "fail"] = "pass" if total >= config.threshold else "fail"

    return ScoreResult(
        total_score=total,
        skill_overlap_score=overlap,
        semantic_similarity_score=semantic,
        weights={
            "skill_overlap": config.skill_overlap_weight,
            "sbert": config.sbert_weight,
        },
        threshold=config.threshold,
        decision=decision,
        disclosure=DISCLOSURE,
    )
