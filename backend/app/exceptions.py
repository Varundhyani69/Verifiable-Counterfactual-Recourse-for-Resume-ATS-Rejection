"""
Custom exception hierarchy for the Verifiable Counterfactual Recourse system.

All domain exceptions inherit from AppError so that global FastAPI handlers
can catch them uniformly and return a consistent {error: {code, message}}
JSON envelope (Property 25).
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all application-level errors."""

    def __init__(self, code: str, message: str, http_status: int = 500) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class ResourceNotFoundError(AppError):
    """Raised when a requested resource does not exist (HTTP 404)."""

    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} '{resource_id}' not found.",
            http_status=404,
        )


class ImmutableRecordError(AppError):
    """
    Raised when code attempts to mutate an append-only record
    (e.g. ExperimentRun) after creation (HTTP 409).
    """

    def __init__(self, record_type: str) -> None:
        super().__init__(
            code="IMMUTABLE_RECORD",
            message=(
                f"{record_type} records are append-only and cannot be modified after creation."
            ),
            http_status=409,
        )


class FileTooLargeError(AppError):
    """Raised when an uploaded file exceeds MAX_FILE_SIZE_MB (HTTP 413)."""

    def __init__(self, max_mb: int) -> None:
        super().__init__(
            code="FILE_TOO_LARGE",
            message=f"Uploaded file exceeds the maximum allowed size of {max_mb} MB.",
            http_status=413,
        )


class UnsupportedFileTypeError(AppError):
    """Raised when an uploaded file is neither PDF nor DOCX (HTTP 415)."""

    def __init__(self) -> None:
        super().__init__(
            code="UNSUPPORTED_FILE_TYPE",
            message="Only PDF and DOCX files are supported.",
            http_status=415,
        )


class EmptyExtractionError(AppError):
    """Raised when text extraction produces zero non-whitespace characters (HTTP 422)."""

    def __init__(self) -> None:
        super().__init__(
            code="EMPTY_EXTRACTION",
            message="Text extraction produced no usable content from the uploaded file.",
            http_status=422,
        )


class ExtractionFailedError(AppError):
    """Raised when the extraction library throws an unexpected exception (HTTP 422)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            code="EXTRACTION_FAILED",
            message=f"Text extraction failed: {detail}",
            http_status=422,
        )


class TextTooLongError(AppError):
    """Raised when manual text or JD text exceeds its character limit (HTTP 422)."""

    def __init__(self, field: str, max_chars: int) -> None:
        super().__init__(
            code="TEXT_TOO_LONG",
            message=f"{field} must not exceed {max_chars:,} characters.",
            http_status=422,
        )


class TextEmptyError(AppError):
    """Raised when a required text body is empty or whitespace-only (HTTP 422)."""

    def __init__(self, field: str) -> None:
        super().__init__(
            code="TEXT_EMPTY",
            message=f"{field} must not be empty.",
            http_status=422,
        )


class SBERTUnavailableError(AppError):
    """Raised when the Sentence-BERT model fails to produce an embedding (HTTP 502)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            code="SBERT_UNAVAILABLE",
            message=f"Sentence-BERT model is unavailable: {detail}",
            http_status=502,
        )


class ExportFailedError(AppError):
    """Raised when file serialization fails during resume export (HTTP 500)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            code="EXPORT_FAILED",
            message=f"Resume export failed: {detail}",
            http_status=500,
        )


class InvalidBaselineMethodError(AppError):
    """Raised when baseline_method is not one of the three allowed values (HTTP 422)."""

    ALLOWED = {"original_resume", "generic_llm", "proposed"}

    def __init__(self, value: str) -> None:
        super().__init__(
            code="INVALID_BASELINE_METHOD",
            message=(
                f"'{value}' is not a valid baseline_method. "
                f"Allowed values: {', '.join(sorted(self.ALLOWED))}."
            ),
            http_status=422,
        )
