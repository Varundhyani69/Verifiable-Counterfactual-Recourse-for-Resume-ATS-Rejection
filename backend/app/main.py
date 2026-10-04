"""
FastAPI application entry point.

Registers all routers and installs global exception handlers that convert
every AppError (and FastAPI's built-in validation errors) into the uniform
{data} / {error: {code, message}} envelope defined in response.py.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.exceptions import AppError
from backend.app.response import error_response
from backend.app.routers import candidates, experiments, job_descriptions, resumes

app = FastAPI(
    title="Verifiable Counterfactual Recourse — ATS Rejection",
    description=(
        "Research system that identifies the smallest truthful, evidence-supported "
        "changes a candidate can make to their resume to cross a simulated ATS threshold."
    ),
    version="0.1.0",
)


# ── Global exception handlers ─────────────────────────────────────────────────


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert Pydantic / FastAPI validation errors to 422 with INVALID_REQUEST code."""
    first_error = exc.errors()[0] if exc.errors() else {}
    message = first_error.get("msg", "Request validation failed.")
    return error_response(code="INVALID_REQUEST", message=message, status_code=422)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert all AppError subclasses to their pre-configured HTTP status + envelope."""
    return error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.http_status,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: return 500 without leaking a stack trace to the client."""
    return error_response(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred. Please try again later.",
        status_code=500,
    )


# ── Health check ──────────────────────────────────────────────────────────────


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe — returns 200 when the application is running."""
    return {"status": "ok"}


# ── Routers (registered here as each module is implemented) ───────────────────
# from backend.app.routers import analysis, recourse
app.include_router(resumes.router, prefix="/api")
app.include_router(experiments.router, prefix="/api")
app.include_router(job_descriptions.router, prefix="/api")
app.include_router(candidates.router, prefix="/api")
# app.include_router(analysis.router, prefix="/api")
# app.include_router(recourse.router, prefix="/api")
