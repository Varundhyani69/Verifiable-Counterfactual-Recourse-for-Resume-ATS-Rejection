"""
Uniform JSON response helpers.

All API endpoints must use these helpers to guarantee the envelope shape
required by Property 25 (API Response Envelope Consistency):

  Success:  {"data": <payload>}           — no top-level "error" key
  Error:    {"error": {"code": "...", "message": "..."}}  — no top-level "data" key

These helpers are the single authoritative source for the envelope structure.
Any deviation from this pattern violates Requirements 13.2–13.5.
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def success_response(data: Any, status_code: int = 200) -> JSONResponse:
    """
    Return a successful JSON response with a top-level ``data`` field.

    Args:
        data: The response payload (dict, list, or scalar).
        status_code: HTTP status code (default 200; use 201 for creation).

    Returns:
        A FastAPI JSONResponse with ``{"data": data}``.
    """
    return JSONResponse(content={"data": data}, status_code=status_code)


def error_response(code: str, message: str, status_code: int = 500) -> JSONResponse:
    """
    Return an error JSON response with a top-level ``error`` field.

    Args:
        code: Machine-readable error code string (e.g. ``"NOT_FOUND"``).
        message: Human-readable explanation of the error.
        status_code: HTTP status code (default 500).

    Returns:
        A FastAPI JSONResponse with ``{"error": {"code": code, "message": message}}``.
    """
    return JSONResponse(
        content={"error": {"code": code, "message": message}},
        status_code=status_code,
    )
