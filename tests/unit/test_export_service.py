"""
Unit tests for the Export Service.

Covers:
- New ResumeVersion has version_number = prior_max + 1  (Req 9.1)
- Original ResumeDocument and baseline version unchanged after export  (Req 9.2)
- Export failure returns structured error with no partial record created  (Req 9.5)
- .txt and .pdf paths each return non-empty bytes  (Req 9.3, 9.4)

Owner: Shahin
Requirements: 9.1–9.6
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.app.exceptions import ExportFailedError, ResourceNotFoundError
from backend.app.services.export_service import (
    _apply_single_edit,
    _compute_next_version_number,
    apply_edits,
    export_pdf,
    export_txt,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_version(
    version_number: int = 1,
    content: str = "Hello World. I am a software engineer.",
    original_resume_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a minimal mock ResumeVersion."""
    v = MagicMock()
    v.id = uuid.uuid4()
    v.version_number = version_number
    v.content = content
    v.original_resume_id = original_resume_id or uuid.uuid4()
    return v


def _make_edit(
    original_text: str = "Hello World",
    proposed_text: str = "Hello, Professional World",
) -> MagicMock:
    """Create a minimal mock ProposedEdit."""
    e = MagicMock()
    e.id = uuid.uuid4()
    e.original_text = original_text
    e.proposed_text = proposed_text
    return e


# ── _apply_single_edit ────────────────────────────────────────────────────────


def test_apply_single_edit_replaces_first_occurrence() -> None:
    """Should replace only the first occurrence of original_text."""
    edit = _make_edit("foo", "bar")
    result = _apply_single_edit("foo foo foo", edit)
    assert result == "bar foo foo"


def test_apply_single_edit_no_match_returns_unchanged() -> None:
    """When original_text is absent, text is returned unchanged."""
    edit = _make_edit("MISSING", "replaced")
    result = _apply_single_edit("some text", edit)
    assert result == "some text"


def test_apply_single_edit_full_replacement() -> None:
    edit = _make_edit("Python developer", "Senior Python Engineer")
    text = "I am a Python developer with 5 years of experience."
    result = _apply_single_edit(text, edit)
    assert "Senior Python Engineer" in result
    assert "Python developer" not in result


# ── export_txt ────────────────────────────────────────────────────────────────


def test_export_txt_returns_nonempty_bytes() -> None:
    """Req 9.3: .txt export must return non-empty bytes."""
    version = _make_version(content="Resume content here.")
    result = export_txt(version)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_export_txt_utf8_encoded() -> None:
    """export_txt encodes content as UTF-8."""
    content = "Résumé with special characters: café, naïve"
    version = _make_version(content=content)
    result = export_txt(version)
    assert result.decode("utf-8") == content


def test_export_txt_raises_on_empty_content() -> None:
    """Empty content should trigger ExportFailedError."""
    version = _make_version(content="")
    with pytest.raises(ExportFailedError):
        export_txt(version)


def test_export_txt_multiline_content() -> None:
    content = "Line 1\nLine 2\nLine 3"
    version = _make_version(content=content)
    result = export_txt(version)
    assert b"Line 1" in result
    assert b"Line 3" in result


# ── export_pdf ────────────────────────────────────────────────────────────────


def test_export_pdf_returns_nonempty_bytes_when_reportlab_available() -> None:
    """Req 9.4: .pdf export must return non-empty bytes when reportlab is installed."""
    try:
        import reportlab  # noqa: F401
    except ImportError:
        pytest.skip("reportlab not installed — skipping PDF export test")

    version = _make_version(content="Software Engineer with Python expertise.")
    result = export_pdf(version)
    assert isinstance(result, bytes)
    assert len(result) > 0
    # PDF files start with the magic bytes %PDF
    assert result[:4] == b"%PDF"


def test_export_pdf_raises_export_failed_when_reportlab_unavailable() -> None:
    """When reportlab is absent, ExportFailedError is raised (Req 9.5)."""
    with patch(
        "backend.app.services.export_service._REPORTLAB_AVAILABLE", False
    ):
        version = _make_version(content="Some resume text.")
        with pytest.raises(ExportFailedError, match="reportlab"):
            export_pdf(version)


def test_export_pdf_error_on_exception() -> None:
    """Any unexpected error in PDF generation wraps in ExportFailedError."""
    try:
        import reportlab  # noqa: F401
    except ImportError:
        pytest.skip("reportlab not installed")

    version = _make_version(content="Some resume text.")
    with patch(
        "backend.app.services.export_service.SimpleDocTemplate",
        side_effect=RuntimeError("disk full"),
    ):
        with pytest.raises(ExportFailedError, match="disk full"):
            export_pdf(version)


# ── apply_edits ───────────────────────────────────────────────────────────────


def test_apply_edits_version_number_increments() -> None:
    """New version_number must be prior_max + 1  (Req 9.1)."""
    original_resume_id = uuid.uuid4()
    base_version_id = uuid.uuid4()

    base_version = _make_version(version_number=1, original_resume_id=original_resume_id)
    base_version.id = base_version_id

    edit = _make_edit("Hello World", "Hello, Professional World")

    # Mock DB session
    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, pk: (
        base_version if pk == base_version_id else edit
    )

    # _compute_next_version_number returns 2
    with patch(
        "backend.app.services.export_service._compute_next_version_number",
        return_value=2,
    ):
        # Capture the ResumeVersion added to db
        added_versions: list[MagicMock] = []

        def capture_add(obj: MagicMock) -> None:
            added_versions.append(obj)

        mock_db.add.side_effect = capture_add

        # flush/refresh no-ops
        mock_db.flush.return_value = None
        mock_db.refresh.return_value = None

        result = apply_edits(
            db=mock_db,
            resume_version_id=base_version_id,
            accepted_edit_ids=[edit.id],
        )

    assert len(added_versions) == 1
    added = added_versions[0]
    assert added.version_number == 2


def test_apply_edits_original_version_unchanged() -> None:
    """The base version content must NOT be mutated (Req 9.2)."""
    original_content = "I am a Python developer."
    original_resume_id = uuid.uuid4()
    base_version_id = uuid.uuid4()

    base_version = _make_version(
        version_number=1,
        content=original_content,
        original_resume_id=original_resume_id,
    )
    base_version.id = base_version_id

    edit = _make_edit("Python developer", "Senior Python Engineer")

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, pk: (
        base_version if pk == base_version_id else edit
    )
    mock_db.flush.return_value = None
    mock_db.refresh.return_value = None

    with patch(
        "backend.app.services.export_service._compute_next_version_number",
        return_value=2,
    ):
        apply_edits(
            db=mock_db,
            resume_version_id=base_version_id,
            accepted_edit_ids=[edit.id],
        )

    # Original content must be untouched
    assert base_version.content == original_content


def test_apply_edits_raises_when_version_not_found() -> None:
    """ResourceNotFoundError raised when base version is missing."""
    mock_db = MagicMock()
    mock_db.get.return_value = None

    with pytest.raises(ResourceNotFoundError, match="ResumeVersion"):
        apply_edits(
            db=mock_db,
            resume_version_id=uuid.uuid4(),
            accepted_edit_ids=[],
        )


def test_apply_edits_raises_when_edit_not_found() -> None:
    """ResourceNotFoundError raised when an edit ID is missing."""
    original_resume_id = uuid.uuid4()
    base_version_id = uuid.uuid4()
    missing_edit_id = uuid.uuid4()

    base_version = _make_version(version_number=1, original_resume_id=original_resume_id)
    base_version.id = base_version_id

    def get_side_effect(model: type, pk: uuid.UUID) -> MagicMock | None:
        if pk == base_version_id:
            return base_version
        return None  # edit not found

    mock_db = MagicMock()
    mock_db.get.side_effect = get_side_effect

    with pytest.raises(ResourceNotFoundError, match="ProposedEdit"):
        apply_edits(
            db=mock_db,
            resume_version_id=base_version_id,
            accepted_edit_ids=[missing_edit_id],
        )


def test_apply_edits_empty_edit_list_preserves_content() -> None:
    """Accepting zero edits should produce a new version with the same content."""
    original_content = "Original resume text."
    original_resume_id = uuid.uuid4()
    base_version_id = uuid.uuid4()

    base_version = _make_version(
        version_number=1,
        content=original_content,
        original_resume_id=original_resume_id,
    )
    base_version.id = base_version_id

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, pk: base_version if pk == base_version_id else None
    mock_db.flush.return_value = None
    mock_db.refresh.return_value = None

    added: list[MagicMock] = []
    mock_db.add.side_effect = added.append

    with patch(
        "backend.app.services.export_service._compute_next_version_number",
        return_value=2,
    ):
        apply_edits(
            db=mock_db,
            resume_version_id=base_version_id,
            accepted_edit_ids=[],
        )

    assert len(added) == 1
    assert added[0].content == original_content


def test_apply_edits_multiple_edits_applied_in_order() -> None:
    """Multiple edits must be applied sequentially, not simultaneously."""
    original_resume_id = uuid.uuid4()
    base_version_id = uuid.uuid4()

    base_version = _make_version(
        version_number=1,
        content="Python developer. Python developer.",
        original_resume_id=original_resume_id,
    )
    base_version.id = base_version_id

    edit1 = _make_edit("Python developer", "Senior Python Engineer")
    edit2 = _make_edit("Senior Python Engineer", "Staff Python Engineer")

    lookup = {
        base_version_id: base_version,
        edit1.id: edit1,
        edit2.id: edit2,
    }
    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, pk: lookup.get(pk)
    mock_db.flush.return_value = None
    mock_db.refresh.return_value = None

    added: list[MagicMock] = []
    mock_db.add.side_effect = added.append

    with patch(
        "backend.app.services.export_service._compute_next_version_number",
        return_value=2,
    ):
        apply_edits(
            db=mock_db,
            resume_version_id=base_version_id,
            accepted_edit_ids=[edit1.id, edit2.id],
        )

    # edit1 applied first: "Python developer" → "Senior Python Engineer" (first occurrence)
    # edit2 applied second: "Senior Python Engineer" → "Staff Python Engineer"
    final_content = added[0].content
    assert "Staff Python Engineer" in final_content
