"""
Shared SQLAlchemy-native enums used across multiple domain models.

Using native PostgreSQL ENUM types (rather than VARCHAR with a CHECK
constraint) gives us database-level enforcement plus type safety in Python.
All enum values match the strings defined in the design spec exactly.
"""

from __future__ import annotations

import enum


class VerificationStatus(str, enum.Enum):
    """
    Four-state verification status for CandidateFact and ProposedEdit.

    - Supported          : directly supported by available evidence
    - PartiallySupported : related evidence exists but full claim not established
    - Unsupported        : no sufficient evidence exists
    - NeedsConfirmation  : evidence is ambiguous or requires candidate verification
    """

    SUPPORTED = "Supported"
    PARTIALLY_SUPPORTED = "Partially Supported"
    UNSUPPORTED = "Unsupported"
    NEEDS_CONFIRMATION = "Needs Confirmation"


class DocumentType(str, enum.Enum):
    """Source format of an ingested ResumeDocument."""

    PDF = "pdf"
    DOCX = "docx"
    MANUAL = "manual"


class ClaimType(str, enum.Enum):
    """Category of a CandidateFact extracted from a resume."""

    SKILL = "skill"
    PROJECT = "project"
    RESPONSIBILITY = "responsibility"
    CERTIFICATION = "certification"
    EXPERIENCE = "experience"
    ACHIEVEMENT = "achievement"


class RequirementType(str, enum.Enum):
    """Category of a JobRequirement extracted from a job description."""

    SKILL = "skill"
    CERTIFICATION = "certification"
    EXPERIENCE = "experience"
    QUALIFICATION = "qualification"
    RESPONSIBILITY = "responsibility"


class ImportanceLevel(str, enum.Enum):
    """Whether a job requirement is mandatory or merely preferred."""

    REQUIRED = "required"
    PREFERRED = "preferred"


class ExtractionType(str, enum.Enum):
    """Whether a requirement was stated directly or inferred by the analyzer."""

    EXPLICIT = "explicit"
    INFERRED = "inferred"


class ATSDecision(str, enum.Enum):
    """Binary ATS screening decision for a ResumeVersion."""

    PASS = "pass"
    FAIL = "fail"


class EditType(str, enum.Enum):
    """The six permitted edit operation types for a ProposedEdit."""

    REPHRASE = "rephrase"
    SURFACE_QUALIFICATION = "surface_qualification"
    REORDER = "reorder"
    NORMALIZE_TERMINOLOGY = "normalize_terminology"
    REORGANIZE_SECTIONS = "reorganize_sections"
    REMOVE_REDUNDANCY = "remove_redundancy"


class BaselineMethod(str, enum.Enum):
    """Which evaluation method was used for an ExperimentRun."""

    ORIGINAL_RESUME = "original_resume"
    GENERIC_LLM = "generic_llm"
    PROPOSED = "proposed"
