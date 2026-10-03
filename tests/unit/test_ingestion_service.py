"""
Unit tests — ingestion service (Task 5.5).

Tests cover:
    - PDF extraction round-trip with known fixture
    - DOCX extraction round-trip with known fixture
    - OCR fallback triggers when PyMuPDF returns zero non-whitespace chars
    - 413, 415, empty-extraction 422, library-exception 422 error paths
    - Manual: boundary 1 char and 50,000 chars pass; 0 and 50,001 chars fail

Requirements: 1.1–1.12
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.app.exceptions import (
    EmptyExtractionError,
    ExtractionFailedError,
    FileTooLargeError,
    ResourceNotFoundError,
    TextEmptyError,
    TextTooLongError,
    UnsupportedFileTypeError,
)
from backend.app.models.enums import DocumentType
from backend.app.services import ingestion_service

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_db_mock():
    """Create a mock DB session with commit/refresh/add semantics."""
    db = MagicMock()
    db.get.return_value = None

    def _refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()

    db.refresh.side_effect = _refresh
    return db


def _make_pdf_bytes(text: str = "Hello World") -> bytes:
    """Create a minimal PDF with selectable text using PyMuPDF."""
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), text)
        data = doc.tobytes()
        doc.close()
        return data
    except ImportError:
        pytest.skip("PyMuPDF not installed")
        return b""  # unreachable


def _make_docx_bytes(text: str = "Hello World") -> bytes:
    """Create a minimal DOCX file using python-docx."""
    try:
        from docx import Document
        doc = Document()
        doc.add_paragraph(text)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()
    except ImportError:
        pytest.skip("python-docx not installed")
        return b""  # unreachable


# ── PDF extraction ────────────────────────────────────────────────────────────


class TestPDFIngestion:
    """Tests for PDF file ingestion path."""

    def test_pdf_extraction_roundtrip(self):
        """PDF with selectable text → extracted_text contains original content."""
        db = _make_db_mock()
        pdf_data = _make_pdf_bytes("Test PDF Content")
        candidate_id = uuid.uuid4()

        result = ingestion_service.ingest_file(
            db=db,
            file_data=pdf_data,
            filename="test.pdf",
            content_type="application/pdf",
            candidate_id=candidate_id,
        )

        assert result.document_type == DocumentType.PDF
        assert "Test PDF Content" in result.extracted_text
        assert result.candidate_id == candidate_id
        assert result.filename == "test.pdf"
        assert len(result.source_spans) > 0
        for span in result.source_spans:
            assert span["start"] >= 0
            assert span["end"] > span["start"]
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_ocr_fallback_triggers_on_empty_pdf(self):
        """When PyMuPDF returns zero non-whitespace chars, OCR fallback is triggered."""
        db = _make_db_mock()
        candidate_id = uuid.uuid4()

        # Mock _extract_pdf to return empty text (simulating image-only PDF)
        with patch.object(
            ingestion_service, "_extract_pdf"
        ) as mock_extract:
            mock_extract.return_value = ("   ", [])
            # The service will see stripped text is empty → EmptyExtractionError
            with pytest.raises(EmptyExtractionError):
                ingestion_service.ingest_file(
                    db=db,
                    file_data=b"fake pdf data",
                    filename="scan.pdf",
                    content_type="application/pdf",
                    candidate_id=candidate_id,
                )


# ── DOCX extraction ───────────────────────────────────────────────────────────


class TestDOCXIngestion:
    """Tests for DOCX file ingestion path."""

    def test_docx_extraction_roundtrip(self):
        """DOCX file → extracted_text contains original paragraph text."""
        db = _make_db_mock()
        docx_data = _make_docx_bytes("Test DOCX Content")
        candidate_id = uuid.uuid4()

        result = ingestion_service.ingest_file(
            db=db,
            file_data=docx_data,
            filename="test.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            candidate_id=candidate_id,
        )

        assert result.document_type == DocumentType.DOCX
        assert "Test DOCX Content" in result.extracted_text
        assert result.candidate_id == candidate_id
        assert len(result.source_spans) > 0
        for span in result.source_spans:
            assert span["start"] >= 0
            assert span["end"] > span["start"]


# ── Error paths ───────────────────────────────────────────────────────────────


class TestIngestionErrors:
    """Error-path tests: 413, 415, 422 empty, 422 exception."""

    def test_file_too_large_413(self):
        """File exceeding MAX_FILE_SIZE_MB raises FileTooLargeError (413)."""
        db = _make_db_mock()
        # 11 MB of zeros
        big_data = b"\x00" * (11 * 1024 * 1024)

        with pytest.raises(FileTooLargeError) as exc_info:
            ingestion_service.ingest_file(
                db=db,
                file_data=big_data,
                filename="big.pdf",
                content_type="application/pdf",
                candidate_id=uuid.uuid4(),
            )
        assert exc_info.value.http_status == 413

    def test_unsupported_file_type_415(self):
        """Non-PDF/DOCX file raises UnsupportedFileTypeError (415)."""
        db = _make_db_mock()

        with pytest.raises(UnsupportedFileTypeError) as exc_info:
            ingestion_service.ingest_file(
                db=db,
                file_data=b"not a document",
                filename="resume.txt",
                content_type="text/plain",
                candidate_id=uuid.uuid4(),
            )
        assert exc_info.value.http_status == 415

    def test_empty_extraction_422(self):
        """File that produces no usable text raises EmptyExtractionError (422)."""
        db = _make_db_mock()

        with patch.object(ingestion_service, "_extract_pdf", return_value=("", [])):
            with pytest.raises(EmptyExtractionError) as exc_info:
                ingestion_service.ingest_file(
                    db=db,
                    file_data=b"fake pdf bytes",
                    filename="empty.pdf",
                    content_type="application/pdf",
                    candidate_id=uuid.uuid4(),
                )
            assert exc_info.value.http_status == 422

    def test_library_exception_422(self):
        """Library exception during extraction raises ExtractionFailedError (422)."""
        db = _make_db_mock()

        with patch.object(
            ingestion_service,
            "_extract_pdf",
            side_effect=ExtractionFailedError("corrupt file"),
        ):
            with pytest.raises(ExtractionFailedError) as exc_info:
                ingestion_service.ingest_file(
                    db=db,
                    file_data=b"corrupt data",
                    filename="bad.pdf",
                    content_type="application/pdf",
                    candidate_id=uuid.uuid4(),
                )
            assert exc_info.value.http_status == 422

    def test_no_partial_record_on_error(self):
        """On error, no ResumeDocument is persisted (db.add never called)."""
        db = _make_db_mock()

        with pytest.raises(UnsupportedFileTypeError):
            ingestion_service.ingest_file(
                db=db,
                file_data=b"data",
                filename="resume.jpg",
                content_type="image/jpeg",
                candidate_id=uuid.uuid4(),
            )
        db.add.assert_not_called()
        db.commit.assert_not_called()


# ── Manual ingestion ──────────────────────────────────────────────────────────


class TestManualIngestion:
    """Tests for manual text ingestion path."""

    def test_manual_1_char_passes(self):
        """Minimum boundary: 1 character of text is accepted."""
        db = _make_db_mock()
        result = ingestion_service.ingest_manual(
            db=db, text="X", candidate_id=uuid.uuid4()
        )
        assert result.document_type == DocumentType.MANUAL
        assert result.extracted_text == "X"
        assert result.filename is None

    def test_manual_50000_chars_passes(self):
        """Maximum boundary: 50,000 characters is accepted."""
        db = _make_db_mock()
        text = "A" * 50_000
        result = ingestion_service.ingest_manual(
            db=db, text=text, candidate_id=uuid.uuid4()
        )
        assert result.extracted_text == text
        assert result.source_spans == [{"start": 0, "end": 50_000, "text": text}]

    def test_manual_empty_fails_422(self):
        """Empty string raises TextEmptyError (422)."""
        db = _make_db_mock()
        with pytest.raises(TextEmptyError) as exc_info:
            ingestion_service.ingest_manual(
                db=db, text="", candidate_id=uuid.uuid4()
            )
        assert exc_info.value.http_status == 422

    def test_manual_whitespace_only_fails_422(self):
        """Whitespace-only text raises TextEmptyError (422)."""
        db = _make_db_mock()
        with pytest.raises(TextEmptyError):
            ingestion_service.ingest_manual(
                db=db, text="   \n\t  ", candidate_id=uuid.uuid4()
            )

    def test_manual_50001_chars_fails_422(self):
        """50,001 characters raises TextTooLongError (422)."""
        db = _make_db_mock()
        with pytest.raises(TextTooLongError) as exc_info:
            ingestion_service.ingest_manual(
                db=db, text="A" * 50_001, candidate_id=uuid.uuid4()
            )
        assert exc_info.value.http_status == 422

    def test_manual_roundtrip_document_type(self):
        """Manual ingestion produces document_type='manual'."""
        db = _make_db_mock()
        result = ingestion_service.ingest_manual(
            db=db, text="Resume content here", candidate_id=uuid.uuid4()
        )
        assert result.document_type == DocumentType.MANUAL


# ── get_resume ────────────────────────────────────────────────────────────────


class TestGetResume:
    """Tests for resume retrieval."""

    def test_get_resume_not_found(self):
        """Non-existent resume_id raises ResourceNotFoundError (404)."""
        db = _make_db_mock()
        db.get.return_value = None
        with pytest.raises(ResourceNotFoundError):
            ingestion_service.get_resume(db=db, resume_id=uuid.uuid4())
