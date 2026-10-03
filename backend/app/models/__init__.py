"""
ORM model registry.

Import all models here so that:
1. Alembic's autogenerate can discover every table via Base.metadata
2. Relationship back-references resolve correctly at app startup
3. Teammates can do: from backend.app.models import ResumeDocument, CandidateFact, ...
"""

from backend.app.models.candidate_fact import CandidateFact  # noqa: F401
from backend.app.models.enums import (  # noqa: F401
    ATSDecision,
    BaselineMethod,
    ClaimType,
    DocumentType,
    EditType,
    ExtractionType,
    ImportanceLevel,
    RequirementType,
    VerificationStatus,
)
from backend.app.models.experiment_run import (  # noqa: F401
    ExperimentRun,
    experiment_run_edits,
)
from backend.app.models.job_description import JobDescription  # noqa: F401
from backend.app.models.job_requirement import JobRequirement  # noqa: F401
from backend.app.models.mixins import (  # noqa: F401
    AppendOnlyMixin,
    TimestampMixin,
    UpdatedAtMixin,
    UUIDPrimaryKeyMixin,
)
from backend.app.models.proposed_edit import (  # noqa: F401
    ProposedEdit,
    proposed_edit_facts,
    proposed_edit_requirements,
)
from backend.app.models.resume_document import ResumeDocument  # noqa: F401
from backend.app.models.resume_version import ResumeVersion  # noqa: F401

__all__ = [
    # Enums
    "ATSDecision",
    "BaselineMethod",
    "ClaimType",
    "DocumentType",
    "EditType",
    "ExtractionType",
    "ImportanceLevel",
    "RequirementType",
    "VerificationStatus",
    # Mixins
    "AppendOnlyMixin",
    "TimestampMixin",
    "UpdatedAtMixin",
    "UUIDPrimaryKeyMixin",
    # Domain models
    "ResumeDocument",
    "CandidateFact",
    "JobDescription",
    "JobRequirement",
    "ResumeVersion",
    "ProposedEdit",
    "ExperimentRun",
    # Junction tables
    "proposed_edit_facts",
    "proposed_edit_requirements",
    "experiment_run_edits",
]
