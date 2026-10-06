# Dhruv — JD analyzer and evidence bank

Branch: `dhruv/jd-analyzer-and-evidence-bank`

PR target: `integration`

Source repository: `dhruv086/Verifiable-Counterfactual-Recourse-for-Resume-ATS-Rejection`

Reviewer and merger: Varun

## Summary

Implemented the JD analyzer and candidate evidence bank for Tasks 7 and 8.
Job descriptions are validated, analyzed with spaCy, and persisted with their
requirements. Each requirement records its category, required/preferred importance,
explicit/inferred extraction type, normalized skills, and exact source offsets.
Section headings and mixed importance clauses are supported. Unknown skill names
retain their spelling. The analyzer returns a warning when no requirements are found.

Evidence retrieval includes current and original claim text, source provenance,
verification status, metadata links, and timestamps. PATCH accepts only claim text
and/or a verification status, checks candidate ownership, validates before updating,
and stamps `updated_at`. The original claim, provenance, and metadata are preserved.
Usable evidence excludes `Unsupported` facts.

The spaCy pin was updated from 3.7.4 to 3.7.5 because 3.7.4's Typer dependency
conflicts with FastAPI 0.111.0's required CLI dependencies.

## Task ID

- [Task 7 — JD analyzer](../.kiro/specs/verifiable-counterfactual-recourse/tasks.md),
  subtasks 7.1–7.4, Requirements 2.1–2.8.
- [Task 8 — Evidence bank](../.kiro/specs/verifiable-counterfactual-recourse/tasks.md),
  subtasks 8.1–8.3, Requirements 3.4–3.9.

## Tests run

Unit tests cover all requirement categories and importance signals, known and unknown
skills, real spaCy parsing, persistence, input boundaries, candidate isolation, and
evidence audit preservation. HTTP tests exercise all four routes and error envelopes
against persisted records. Properties 4, 5, and 7 each run 100 generated examples.

```powershell
.venv/Scripts/python.exe -m pytest tests/ -ra
```

After rebasing onto `origin/integration`: **139 passed**, no failures or skipped
tests, with two dependency deprecation warnings. Repository-wide Ruff passes.
The six new backend modules passed the focused strict mypy check. Repository-wide
mypy reports an existing type error in `storage.py:45`, outside Tasks 7 and 8.

The branch is rebased onto `origin/integration` and contains only Dhruv's Tasks 7
and 8 changes. PR submission uses the same branch name in Dhruv's existing fork,
because the account does not have permission to push to the team repository.
This file provides the required PR description. CI and teammate review remain
part of the PR review process.

## Downstream dependencies

- ATS scorer (Task 9): normalized JD skills and structured requirements.
- Recourse engine and optimizer (Tasks 10–11): JD requirements and usable facts.
- Verifier and explanation service (Tasks 12–13): evidence and provenance.
- Evidence review and input screens (Tasks 15–16): the new HTTP endpoints.
- API integration and E2E tests (Tasks 17 and 21): the JD and evidence workflow.

## API output

| Method | Endpoint | Output |
|---|---|---|
| POST | `/api/job-descriptions` | 201, `{data}` containing persisted JD and requirements; warning when extraction is empty |
| GET | `/api/job-descriptions/{id}` | 200, `{data}` containing JD and requirements; 404 when missing |
| GET | `/api/candidates/{id}/evidence` | 200, `{data: {candidate_id, facts}}`; 404 for an unknown candidate |
| PATCH | `/api/candidates/{id}/evidence/{fact_id}` | 200, `{data}` containing the updated fact; 404 or 422 on invalid requests |

For example, submitting `{"text": "Python required and JS preferred"}` extracts
two requirements: Python is `required`; JavaScript is `preferred`. Source spans
point to the original phrases in the submitted text.

PATCH example: `{"claim_text": "Built Python APIs.", "verification_status": "Supported"}`.
An empty object, explicit null, invalid status, blank text, text longer than 2,000
characters, and attempts to patch original claim/provenance fields return 422.

The no-requirements POST response includes `data.warning` as shown in the design
contract and also a top-level `warning` as required by Requirement 2.7.

## Running locally

Activate a Python 3.11 environment and install the project dependencies. Install the
spaCy model with `python -m spacy download en_core_web_sm`. Set `DATABASE_URL` for
PostgreSQL, apply migrations with `alembic upgrade head`, and start the API with
`python -m uvicorn backend.app.main:app --reload`. The routes appear in `/docs`.

Tests use an isolated SQLite database with translated test DDL and do not require
a running PostgreSQL server. Production database migrations were not changed.
