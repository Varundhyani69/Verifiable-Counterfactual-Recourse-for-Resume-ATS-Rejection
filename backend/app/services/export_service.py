"""
Export Service.

Applies accepted recourse edits to produce a new ResumeVersion, then
serialises that version to plain text or PDF for download.

Public API:
    apply_edits(db, resume_version_id, accepted_edit_ids) → ResumeVersion
    export_txt(version)                                    → bytes
    export_pdf(version)                                    → bytes

Rules (Requirements 9.1–9.6):
  - New ResumeVersion gets version_number = max_existing + 1  (Req 9.1)
  - The original ResumeDocument and version_number=1 are NEVER modified (Req 9.2)
  - On any serialisation failure, return a structured error and create no partial record (Req 9.5)
  - Accepted session is recorded in ExperimentRun (Req 9.6)

Owner: Shahin · Branch: shahin/export-comparison-dashboard-e2e
"""

from __future__ import annotations

import io
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.exceptions import ExportFailedError, ResourceNotFoundError
from backend.app.models.proposed_edit import ProposedEdit
from backend.app.models.resume_version import ResumeVersion

# Optional reportlab import — guarded so unit tests without reportlab still work.
try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    _REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _REPORTLAB_AVAILABLE = False


# ── Core helpers ──────────────────────────────────────────────────────────────


def _apply_single_edit(text: str, edit: ProposedEdit) -> str:
    """
    Apply one ProposedEdit to *text* by replacing the first occurrence of
    ``original_text`` with ``proposed_text``.

    If ``original_text`` is not found (can happen with reorder / reorganize
    edit types that reference section headings rather than verbatim text), the
    text is returned unchanged — the caller accumulates all edits sequentially.
    """
    if edit.original_text in text:
        return text.replace(edit.original_text, edit.proposed_text, 1)
    return text


def _compute_next_version_number(db: Session, original_resume_id: uuid.UUID) -> int:
    """Return max(version_number) + 1 for the given resume_document FK."""
    result = db.execute(
        select(func.max(ResumeVersion.version_number)).where(
            ResumeVersion.original_resume_id == original_resume_id
        )
    ).scalar_one_or_none()
    return (result or 0) + 1


# ── Public API ────────────────────────────────────────────────────────────────


def apply_edits(
    *,
    db: Session,
    resume_version_id: uuid.UUID,
    accepted_edit_ids: list[uuid.UUID],
) -> ResumeVersion:
    """
    Apply accepted edits to the given ResumeVersion and persist a new version.

    Steps:
        1. Load the base ResumeVersion and its parent ResumeDocument.
        2. Load the requested ProposedEdits and apply them in order.
        3. Compute the next version_number (max_existing + 1).
        4. Persist the new ResumeVersion and flush — never modify the original.
        5. Return the new ResumeVersion.

    Args:
        db:                Active SQLAlchemy session.
        resume_version_id: UUID of the base ResumeVersion (typically v1).
        accepted_edit_ids: Ordered list of ProposedEdit UUIDs to apply.

    Returns:
        The newly created ResumeVersion.

    Raises:
        ResourceNotFoundError: Base version or any edit not found.

    Requirements: 9.1, 9.2
    """
    # ── Load base version ─────────────────────────────────────────────────
    base_version = db.get(ResumeVersion, resume_version_id)
    if base_version is None:
        raise ResourceNotFoundError("ResumeVersion", str(resume_version_id))

    # ── Load and order edits ──────────────────────────────────────────────
    edits: list[ProposedEdit] = []
    for edit_id in accepted_edit_ids:
        edit = db.get(ProposedEdit, edit_id)
        if edit is None:
            raise ResourceNotFoundError("ProposedEdit", str(edit_id))
        edits.append(edit)

    # ── Apply edits sequentially to the base content ──────────────────────
    revised_content = base_version.content
    for edit in edits:
        revised_content = _apply_single_edit(revised_content, edit)

    # ── Compute next version number ───────────────────────────────────────
    next_version_number = _compute_next_version_number(
        db, base_version.original_resume_id
    )

    # ── Persist new version ───────────────────────────────────────────────
    new_version = ResumeVersion(
        original_resume_id=base_version.original_resume_id,
        version_number=next_version_number,
        content=revised_content,
        ats_score=None,   # Caller (router) may update this after re-scoring
        decision=None,
    )
    db.add(new_version)
    db.flush()
    db.refresh(new_version)

    return new_version


def export_txt(version: ResumeVersion) -> bytes:
    """
    Serialise a ResumeVersion to plain UTF-8 text bytes.

    Args:
        version: The ResumeVersion whose content to export.

    Returns:
        Non-empty bytes containing the resume text encoded as UTF-8.

    Raises:
        ExportFailedError: If serialisation produces empty output or fails.

    Requirements: 9.3, 9.4, 9.5
    """
    try:
        result = version.content.encode("utf-8")
        if not result:
            raise ExportFailedError("Text serialisation produced empty output.")
        return result
    except ExportFailedError:
        raise
    except Exception as exc:
        raise ExportFailedError(str(exc)) from exc


def export_pdf(version: ResumeVersion) -> bytes:
    """
    Serialise a ResumeVersion to PDF bytes using reportlab.

    Layout: letter-size page with 1-inch margins; body text wrapped at 80
    characters per line; monospace-style paragraphs separated by blank lines.

    Args:
        version: The ResumeVersion whose content to export.

    Returns:
        Non-empty PDF bytes.

    Raises:
        ExportFailedError: If reportlab is unavailable, or serialisation fails.

    Requirements: 9.3, 9.4, 9.5
    """
    if not _REPORTLAB_AVAILABLE:
        raise ExportFailedError(
            "reportlab is not installed. Install the project with: pip install -e '.[dev]'"
        )
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=LETTER,
            leftMargin=1 * inch,
            rightMargin=1 * inch,
            topMargin=1 * inch,
            bottomMargin=1 * inch,
        )
        styles = getSampleStyleSheet()
        normal = styles["Normal"]

        story = []
        # Split on blank lines to preserve paragraph structure
        paragraphs = version.content.split("\n\n")
        for para in paragraphs:
            # Escape HTML special characters for reportlab
            safe = (
                para
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                # Preserve single newlines as line breaks within a paragraph
                .replace("\n", "<br/>")
            )
            if safe.strip():
                story.append(Paragraph(safe, normal))
                story.append(Spacer(1, 0.12 * inch))

        doc.build(story)
        pdf_bytes = buffer.getvalue()

        if not pdf_bytes:
            raise ExportFailedError("PDF serialisation produced empty output.")
        return pdf_bytes

    except ExportFailedError:
        raise
    except Exception as exc:
        raise ExportFailedError(str(exc)) from exc
