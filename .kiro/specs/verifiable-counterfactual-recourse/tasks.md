# Implementation Plan: Verifiable Counterfactual Recourse for Resume–ATS Rejection

## Solo Ownership Model

Every task has exactly one owner. No shared epics. Varun integrates everything at the end.

| Person | Solo responsibility |
|---|---|
| **Varun** | Project skeleton, DB schema + ORM, storage backend, recourse engine, optimizer, research CLI, final integration |
| **Vaishnavi** | ATS scorer, evidence verifier, explanation service |
| **Vipul** | Resume ingestion service, evidence extractor, experiment logger |
| **Dhruv** | JD analyzer, evidence bank CRUD |
| **Yash** | Frontend setup + routing, Resume/JD input screen, evidence review screen, ATS analysis screen, recommendations screen, API integration tests |
| **Shahin** | Final resume comparison screen, export service, research evaluation dashboard, E2E tests |

**Branch naming**: `<owner>/<task-slug>` (e.g., `varun/db-schema`, `vipul/ingestion-service`)

**All branches target `integration`. Only Varun merges into `integration` and `main`.**

**Definition of Done** (all five conditions required per Req 15.5):
1. All acceptance criteria for the task are implemented and verified
2. All unit tests for the task pass locally
3. Branch rebased on latest `integration` with no conflicts
4. PR description complete (summary, task ID link, test results, downstream dependencies)
5. CI checks pass (ruff + mypy + pytest / eslint + tsc + vitest)

---

## How to open a Pull Request

1. Branch off `integration`: `git checkout integration && git pull && git checkout -b <your-name>/<task-slug>`
2. Build your task. Run tests locally until they pass.
3. Rebase before opening PR: `git fetch origin && git rebase origin/integration`
4. Push: `git push -u origin <your-name>/<task-slug>`
5. Open a PR on GitHub targeting `integration` (NOT `main`)
6. Fill the PR template:
   - **Summary**: what changed
   - **Task ID**: link to the task in this file (e.g., `tasks.md Task 4`)
   - **Tests run**: paste output of `pytest tests/` or `vitest run`
   - **Downstream dependencies**: list any other modules that depend on this PR being merged
7. Request review from at least one teammate
8. **Varun reviews and merges** — nobody else merges into `integration`

---

## Tasks

---

## Milestone 1 — Project Foundation

> **Owner: Varun**
> Gate: Varun merges into `integration` before anyone else starts.

---

- [ ] 1. Project skeleton, CI pipeline, and shared infrastructure
  - **Owner: Varun** · Branch: `varun/project-skeleton`
  - Create repo directory layout: `backend/`, `frontend/`, `tests/`, `alembic/`, `.github/`
  - Create `pyproject.toml` with pinned deps:
    `fastapi==0.111.0`, `sqlalchemy==2.0.30`, `alembic==1.13.1`, `pydantic==2.7.1`,
    `psycopg2-binary==2.9.9`, `hypothesis==6.100.1`, `pytest==8.2.0`,
    `pytest-cov==5.0.0`, `ruff==0.4.4`, `mypy==1.10.0`,
    `sentence-transformers==2.7.0`, `spacy==3.7.4`, `pymupdf==1.24.3`,
    `python-docx==1.1.0`, `pytesseract==0.3.10`, `Pillow==10.3.0`,
    `reportlab==4.1.0`, `transformers==4.40.1`
  - Create `.env.example` documenting all env vars (no real secrets):
    `DATABASE_URL`, `UPLOAD_DIR`, `MAX_FILE_SIZE_MB`, `MAX_MANUAL_CHARS`,
    `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`,
    `LLM_API_KEY`, `LLM_MODEL`
  - Create `backend/app/main.py` with FastAPI app and global exception handlers for
    `RequestValidationError`, `ResourceNotFoundError`, `ImmutableRecordError`,
    and unhandled `Exception`
  - Create `backend/app/exceptions.py` defining `ResourceNotFoundError`,
    `ImmutableRecordError`, `AppError` base class
  - Create `backend/app/response.py` with `success_response(data)` and
    `error_response(code, message)` helpers enforcing `{data}` / `{error: {code, message}}`
    envelope (Property 25)
  - Configure `ruff` and `mypy` in `pyproject.toml`
  - Create `.github/workflows/ci.yml`: backend job (ruff, mypy, pytest) + frontend job
    (eslint, tsc, vitest)
  - _Requirements: 13.6, 15.1, 15.5_

  - [ ] 1.1 Bootstrap skeleton, exceptions, response helpers, and CI
    - Verify `ruff check .` and `mypy backend/` pass on empty stubs
    - _Requirements: 13.6, 15.1_

  - [ ]* 1.2 Property test — API response envelope consistency (Property 25)
    - `Feature: verifiable-counterfactual-recourse, Property 25`
    - Generate arbitrary success payloads and error codes; assert `data` and `error`
      are mutually exclusive top-level keys
    - **Validates: Requirements 13.2, 13.3, 13.4, 13.5**

---

- [ ] 2. Database schema migrations and SQLAlchemy ORM models
  - **Owner: Varun** · Branch: `varun/db-schema`
  - Set up `alembic/`, `alembic.ini`, `alembic/env.py` connected to `DATABASE_URL`
  - Create `backend/app/models/` package with one file per domain entity
  - Implement `CREATE TYPE verification_status_enum AS ENUM (...)` migration
  - Implement migrations for all 9 tables + 3 junction tables:
    `resume_documents`, `candidate_facts` (CHECK len ≤ 2000, FK CASCADE, DB enum),
    `job_descriptions`, `job_requirements` (CHECK importance, extraction_type),
    `resume_versions` (UNIQUE(original_resume_id, version_number)),
    `proposed_edits`, `proposed_edit_facts`, `proposed_edit_requirements`,
    `experiment_runs`, `experiment_run_edits`
  - Write SQLAlchemy ORM model classes for every table and junction table
  - Write `AppendOnlyMixin` that raises `ImmutableRecordError` on any post-creation
    `__setattr__` call on `ExperimentRun`
  - _Requirements: 14.1–14.7, 10.8_

  - [ ] 2.1 Implement all Alembic migrations and ORM model classes
    - Run `alembic upgrade head` on a fresh DB; confirm zero errors
    - Verify FK CASCADE: deleting a `ResumeDocument` deletes its `CandidateFact` rows
    - Verify UNIQUE constraint raises `IntegrityError` on duplicate `(original_resume_id, version_number)`
    - Verify DB enum rejects an out-of-range `verification_status` value
    - Verify `AppendOnlyMixin` raises `ImmutableRecordError` on mutation
    - _Requirements: 14.1–14.7, 10.8_

  - [ ]* 2.2 Unit tests — ORM integrity constraints
    - Test FK cascade delete (Req 14.6)
    - Test DB enum rejects invalid `verification_status` (Req 14.7)
    - Test UNIQUE(original_resume_id, version_number) raises `IntegrityError` on duplicate
    - Test `AppendOnlyMixin` raises `ImmutableRecordError` on post-creation mutation
    - _Requirements: 14.6, 14.7, 10.8_

---

- [ ] 3. Storage backend abstraction
  - **Owner: Varun** · Branch: `varun/storage-backend`
  - Create `backend/app/storage.py` with `StorageBackend` Protocol and two
    implementations: `LocalFileStorage` (writes to `UPLOAD_DIR` env var) and
    `S3CompatibleStorage` (activates when `S3_ENDPOINT_URL` is set)
  - Implement FastAPI file-size enforcement middleware; reject before handler with
    HTTP 413 when upload exceeds `MAX_FILE_SIZE_MB`
  - _Requirements: 1.6_

  - [ ] 3.1 Implement StorageBackend protocol, LocalFileStorage, and size middleware
    - Write unit tests for `save`/`load`/`delete` round-trip on `LocalFileStorage`
    - _Requirements: 1.6_

---

- [ ] 4. CONTRIBUTING.md and README dependency graph
  - **Owner: Varun** · Branch: `varun/contributing-guide`
  - Create `CONTRIBUTING.md` at repository root documenting:
    - Branch naming convention per teammate (Req 15.2)
    - PR description template: (a) summary, (b) task ID link, (c) tests run and
      pass/fail status, (d) downstream dependencies (Req 15.3)
    - Merge rules: all PRs target `integration`; only Varun merges (Req 15.1, 15.4)
    - Minimum one approving review before Varun merges (Req 15.4)
    - Definition of Done checklist (Req 15.5)
    - Integration milestone dependency graph (Req 15.6)
    - Milestone gate descriptions (Req 15.7)
    - Environment setup: Python env, SBERT model download, spaCy model download,
      PostgreSQL setup, `alembic upgrade head`, `npm install` in `frontend/`
  - Update `README.md` with module dependency graph
  - _Requirements: 15.1–15.7_

  - [ ] 4.1 Write CONTRIBUTING.md and update README with dependency graph
    - _Requirements: 15.1–15.7_

---

## Milestone 2 — Backend Services (Parallel after Milestone 1)

> All four backend owners work independently in parallel after Milestone 1 is merged.

---

### Vipul — Resume Ingestion + Evidence Extractor

- [ ] 5. Resume ingestion service
  - **Owner: Vipul** · Branch: `vipul/ingestion-service`
  - Implement `backend/app/services/ingestion_service.py`:
    - `ingest_file(file, candidate_id) → ResumeDocument`
    - `ingest_manual(text, candidate_id) → ResumeDocument`
    - `get_resume(resume_id) → ResumeDocument`
  - Implement `SourceSpan(start: int, end: int)` and `ExtractedSegment` Pydantic models
  - DOCX → `python-docx` with cumulative char offset tracking
  - PDF with selectable text → `PyMuPDF` with cumulative char offset tracking
  - PDF with no selectable text (PyMuPDF returns zero non-whitespace chars) → `pytesseract` OCR fallback
  - Error paths: HTTP 413 (>10 MB), 415 (not PDF/DOCX), 422 (empty extraction or
    library exception) — each returning `{error: {code, message}}`, no partial record
  - Manual text: accept 1–50,000 chars; 422 on empty or >50,000 chars
  - Wire `POST /api/resumes/upload`, `POST /api/resumes/manual`, `GET /api/resumes/{id}`
  - _Requirements: 1.1–1.12_

  - [ ] 5.1 Implement ingestion service with PDF, DOCX, OCR, and manual paths
    - _Requirements: 1.1–1.12_

  - [ ]* 5.2 Property test — source span validity (Property 1)
    - `Feature: verifiable-counterfactual-recourse, Property 1`
    - Generate arbitrary document texts; assert every span satisfies
      `0 ≤ start < end ≤ len(extracted_text)`
    - **Validates: Requirements 1.2, 2.4, 3.2**

  - [ ]* 5.3 Property test — extraction error envelope consistency (Property 2)
    - `Feature: verifiable-counterfactual-recourse, Property 2`
    - For each failure mode (oversized, bad MIME, empty extraction, exception),
      assert response contains `error.code` and `error.message`; assert no
      `ResumeDocument` row created in DB
    - **Validates: Requirements 1.6, 1.7, 1.8, 1.9**

  - [ ]* 5.4 Property test — manual ingestion round trip (Property 3)
    - `Feature: verifiable-counterfactual-recourse, Property 3`
    - Generate arbitrary strings 1–50,000 chars; POST to `/api/resumes/manual`;
      GET `/api/resumes/{id}`; assert `extracted_text` equals input and
      `document_type == "manual"`
    - **Validates: Requirements 1.10, 1.12**

  - [ ]* 5.5 Unit tests — ingestion service
    - Test PDF extraction round-trip with known fixture
    - Test DOCX extraction round-trip with known fixture
    - Test OCR fallback triggers when PyMuPDF returns zero non-whitespace chars
    - Test 413, 415, empty-extraction 422, library-exception 422 error paths
    - Test manual: boundary 1 char and 50,000 chars pass; 0 and 50,001 chars fail
    - _Requirements: 1.1–1.12_

---

- [ ] 6. Evidence extractor
  - **Owner: Vipul** · Branch: `vipul/evidence-extractor`
  - Implement `backend/app/services/evidence_extractor.py`:
    - `extract(resume: ResumeDocument) → list[CandidateFact]`
  - Use spaCy NER pipeline to classify claims into 6 types:
    `skill`, `project`, `responsibility`, `certification`, `experience`, `achievement`
  - Set `verification_status = "Needs Confirmation"` on every auto-extracted fact
  - Set `original_claim_text = claim_text` at creation; never mutate after
  - Record `source_span = {start, end}` from spaCy token character positions
  - Trigger extraction automatically on successful ingestion (Task 5)
  - _Requirements: 3.1, 3.2, 3.3_

  - [ ] 6.1 Implement evidence extractor with spaCy NLP pipeline
    - _Requirements: 3.1–3.3_

  - [ ]* 6.2 Property test — CandidateFact field completeness (Property 6)
    - `Feature: verifiable-counterfactual-recourse, Property 6`
    - Generate arbitrary resume texts; run extractor; for every returned fact assert
      all 9 required fields are non-null and `verification_status == "Needs Confirmation"`
    - **Validates: Requirements 3.2, 3.3**

  - [ ]* 6.3 Unit tests — evidence extractor
    - Test all 6 claim types are producible from crafted resume text
    - Test `original_claim_text == claim_text` at creation
    - Test `verification_status == "Needs Confirmation"` for every extracted fact
    - Test `source_span.start < source_span.end` for every fact
    - _Requirements: 3.1–3.3_

---

### Dhruv — JD Analyzer + Evidence Bank

- [ ] 7. JD analyzer
  - **Owner: Dhruv** · Branch: `dhruv/jd-analyzer`
  - Implement `backend/app/services/jd_analyzer.py`:
    - `analyze(jd_text: str) → tuple[JobDescriptionRecord, list[JobRequirement]]`
    - `get_jd(jd_id: UUID) → JobDescriptionRecord`
  - spaCy NLP pipeline: NER + dependency parsing for signal word detection
  - Signal word mapping:
    `{"must have","required","must"} → "required"`,
    `{"preferred","nice to have","desired","plus"} → "preferred"`,
    default when no signal words found → `"required"`
  - Skill canonicalization: hardcoded map (e.g., `"JS" → "JavaScript"`) + spaCy
    entity linking; if no mapping exists, preserve original name unchanged
  - Classify each requirement as `explicit` (direct phrase) or `inferred` (NLP-derived)
  - Record `{start, end}` char offsets from spaCy token spans
  - Return `warning` field when zero requirements extracted (not an error)
  - Validate 1–10,000 chars; return 422 on empty/whitespace-only body
  - Wire `POST /api/job-descriptions` and `GET /api/job-descriptions/{id}`
  - _Requirements: 2.1–2.8_

  - [ ] 7.1 Implement JD analyzer with NLP pipeline, importance, and normalization
    - _Requirements: 2.1–2.8_

  - [ ]* 7.2 Property test — JobRequirement importance invariant (Property 4)
    - `Feature: verifiable-counterfactual-recourse, Property 4`
    - Generate JD texts with and without signal words; assert `importance` is
      always exactly `"required"` or `"preferred"`; assert no-signal-word
      requirements default to `"required"`
    - **Validates: Requirements 2.3**

  - [ ]* 7.3 Property test — skill normalization completeness (Property 5)
    - `Feature: verifiable-counterfactual-recourse, Property 5`
    - For every `JobRequirement` returned, assert `normalized_skills` is non-empty
      and every entry is a non-empty string
    - **Validates: Requirements 2.6**

  - [ ]* 7.4 Unit tests — JD analyzer
    - Test each of the 8 known signal words maps to the correct importance
    - Test default `"required"` when no signal words present
    - Test canonical mapping `"JS" → "JavaScript"`
    - Test unknown skill is preserved unchanged
    - Test `explicit` vs `inferred` distinction
    - Test `warning` field present when zero requirements extracted
    - Test 422 on empty and whitespace-only body
    - _Requirements: 2.1–2.8_

---

- [ ] 8. Evidence bank
  - **Owner: Dhruv** · Branch: `dhruv/evidence-bank`
  - Implement `backend/app/services/evidence_bank.py`:
    - `get_facts(candidate_id: UUID) → list[CandidateFact]`
    - `update_fact(candidate_id: UUID, fact_id: UUID, patch: CandidateFactPatch) → CandidateFact`
    - `get_usable_facts(candidate_id: UUID) → list[CandidateFact]`
      (returns facts where `verification_status != "Unsupported"`)
  - Implement `CandidateFactPatch` Pydantic model: optional `claim_text` (1–2000 chars,
    non-empty) and optional `verification_status` (one of the 4 valid values);
    return 422 on any violation
  - Stamp `updated_at` on every successful PATCH
  - Never mutate `original_claim_text` under any PATCH operation
  - Wire `GET /api/candidates/{id}/evidence` and `PATCH /api/candidates/{id}/evidence/{fact_id}`
  - _Requirements: 3.4–3.9_

  - [ ] 8.1 Implement evidence bank CRUD with PATCH validation and audit trail
    - _Requirements: 3.4–3.9_

  - [ ]* 8.2 Property test — original_claim_text immutability (Property 7)
    - `Feature: verifiable-counterfactual-recourse, Property 7`
    - Generate arbitrary sequences of PATCH operations (valid and invalid);
      assert `original_claim_text` remains byte-for-byte identical to its creation-time value
    - **Validates: Requirements 3.9**

  - [ ]* 8.3 Unit tests — evidence bank
    - Test `get_usable_facts` excludes `Unsupported` facts
    - Test PATCH 422 on invalid status, empty `claim_text`, `claim_text` > 2000 chars
    - Test `updated_at` is stamped on successful PATCH
    - Test `original_claim_text` unchanged after multiple PATCHes
    - _Requirements: 3.5–3.9_

---

### Vaishnavi — ATS Scorer

- [ ] 9. ATS scorer
  - **Owner: Vaishnavi** · Branch: `vaishnavi/ats-scorer`
  - Implement `backend/app/services/ats_scorer.py`:
    - `score(resume_text: str, jd_text: str, config: ScoringConfig) → ScoreResult`
  - `ScoringConfig`: `skill_overlap_weight=0.5`, `sbert_weight=0.5` (must sum to 1.0),
    `threshold=0.5` (range [0.0, 1.0]), `sbert_model_name="all-MiniLM-L6-v2"`
  - `ScoreResult`: `total_score`, `skill_overlap_score`, `semantic_similarity_score`,
    `weights`, `threshold`, `decision` (`"pass"` iff `total_score >= threshold`)
  - Load SBERT model once at app startup; reuse for all requests (determinism)
  - Skill overlap: `|intersection(resume_skills, jd_skills)| / |union(resume_skills, jd_skills)|`
  - Semantic similarity: cosine similarity of SBERT embeddings
  - Store each result as a `ResumeVersion` with `version_number = 1` for baseline;
    each subsequent version increments by 1
  - Return 404 if `resume_id` or `job_description_id` not found
  - Return 502 if SBERT model fails to produce an embedding
  - Return 422 if weights don't sum to 1.0 or threshold is out of [0.0, 1.0]
  - Include `disclosure` string in every response (Req 4.9)
  - Wire `POST /api/analysis`
  - _Requirements: 4.1–4.9_

  - [ ] 9.1 Implement ATS scorer, ScoringConfig, ScoreResult, and POST /api/analysis
    - _Requirements: 4.1–4.9_

  - [ ]* 9.2 Property test — ATS score range and decision consistency (Property 8)
    - `Feature: verifiable-counterfactual-recourse, Property 8`
    - Generate arbitrary (resume_text, jd_text, weight, threshold); assert
      `total_score` ∈ [0.0, 1.0] and `decision == "pass" iff total_score >= threshold`
    - **Validates: Requirements 4.1, 4.3**

  - [ ]* 9.3 Property test — ATS scorer determinism (Property 9)
    - `Feature: verifiable-counterfactual-recourse, Property 9`
    - Call `score()` twice with identical inputs; assert every field of both results
      is identical
    - **Validates: Requirements 4.5**

  - [ ]* 9.4 Property test — ResumeVersion monotonic numbering (Property 10)
    - `Feature: verifiable-counterfactual-recourse, Property 10`
    - Create multiple scoring calls for the same `original_resume_id`; assert
      `version_number` is a gapless, strictly increasing sequence starting at 1
    - **Validates: Requirements 4.6, 9.1**

  - [ ]* 9.5 Unit tests — ATS scorer
    - Test `total_score` ∈ [0.0, 1.0] with boundary inputs
    - Test weights summing to ≠ 1.0 returns 422
    - Test `decision == "pass"` iff `total_score >= threshold` including equality
    - Test 502 error response shape when SBERT fails (mocked)
    - Test 404 on invalid `resume_id` and `job_description_id`
    - Test `disclosure` string present in response
    - _Requirements: 4.1–4.9_

---

## Milestone 3 — Core Research Services

> **Owner: Varun** (recourse engine + optimizer) and **Vaishnavi** (verifier + explanation)
> work solo in parallel after Milestone 2 is merged.

---

### Varun — Recourse Engine + Optimizer

- [ ] 10. Recourse engine
  - **Owner: Varun** · Branch: `varun/recourse-engine`
  - Implement `backend/app/services/recourse_engine.py`:
    - `generate(resume_version, jd_id, usable_facts, requirements) → RecourseResult`
  - Implement all 6 edit type handlers:
    - `rephrase`: synonym/style replacement; SBERT cosine between `original_text` and
      `proposed_text` must be ≥ 0.85; discard if below threshold
    - `surface_qualification`: promote a buried but valid fact to a prominent position
    - `reorder`: change order of bullets or sections
    - `normalize_terminology`: apply canonical skill name from JD normalization map
    - `reorganize_sections`: move a section to a different resume position
    - `remove_redundancy`: remove a duplicate claim
  - Fabrication guard: after drafting each candidate edit, run spaCy NER on
    `proposed_text`; discard any edit containing an entity absent from the Evidence Bank
  - Never use a `CandidateFact` with `verification_status = "Unsupported"` as grounding
  - Discard any edit that cannot be linked to at least one `JobRequirement`
  - Cap at 20 edits per request
  - Return `infeasible` response with `reason` ∈ `{no_evidence, all_unsupported, no_requirement_match}`
    when no valid edits can be generated
  - Store each `ProposedEdit` with `edit_cost = 0.0` placeholder (Optimizer fills final cost)
  - Wire `POST /api/recourse/generate`
  - _Requirements: 5.1–5.8_

  - [ ] 10.1 Implement recourse engine with 6 edit types and fabrication guard
    - _Requirements: 5.1–5.8_

  - [ ]* 10.2 Property test — ProposedEdit type and grounding invariants (Property 11)
    - `Feature: verifiable-counterfactual-recourse, Property 11`
    - For every generated edit: assert `edit_type` is one of 6 valid values;
      all referenced facts have `verification_status ≠ "Unsupported"`;
      `len(job_requirement_ids) ≥ 1`; `len(evidence_fact_ids) ≥ 1`
    - **Validates: Requirements 5.1, 5.2, 5.6**

  - [ ]* 10.3 Property test — no fabrication in proposed edits (Property 12)
    - `Feature: verifiable-counterfactual-recourse, Property 12`
    - For every generated edit, assert every named entity in `proposed_text` appears
      in at least one of the linked `CandidateFact` records
    - **Validates: Requirements 5.3, 6.7**

  - [ ]* 10.4 Property test — rephrase semantic preservation (Property 13)
    - `Feature: verifiable-counterfactual-recourse, Property 13`
    - For any `rephrase` edit, assert SBERT cosine similarity between
      `original_text` and `proposed_text` ≥ 0.85
    - **Validates: Requirements 5.4**

  - [ ]* 10.5 Unit tests — recourse engine
    - Test each of the 6 edit types is producible from crafted inputs
    - Test fabrication guard: edit introducing an unknown entity is discarded
    - Test `Unsupported` fact is never the sole grounding evidence
    - Test rephrase with SBERT < 0.85 is rejected (mocked SBERT)
    - Test infeasible `no_evidence`, `all_unsupported`, `no_requirement_match` paths
    - Test cap: at most 20 edits returned
    - _Requirements: 5.1–5.8_

---

- [ ] 11. Optimizer
  - **Owner: Varun** · Branch: `varun/optimizer`
  - Implement `backend/app/services/optimizer.py`:
    - `optimize(edits, resume, config: OptimizationConfig) → OptimizationResult`
  - `OptimizationConfig`: four weights defaulting to 0.25 each, `threshold = 0.5`
  - Edit cost formula per edit:
    ```
    C(e) = w1 × norm_levenshtein(original, proposed)
         + w2 × (changed_statements / total_statements)
         + w3 × (1 − SBERT_cosine(original, proposed))
         + w4 × (moved_sections / total_sections)
    ```
    where w1=w2=w3=w4=0.25 by default; all configurable per `ExperimentRun`
  - Implement `BoundedSubsetSearch`: sort edits ascending by cost → enumerate subsets
    smallest-first → apply subset → score with ATS_Scorer → check structural constraints
    → check fabrication → track best feasible
  - Structural constraints on revised resume: all named sections preserved, contact
    block unchanged, every `CandidateFact` represented
  - Minimality post-processing: remove any edit that is redundant while still crossing threshold
  - On infeasible: return `status = "infeasible"`, `constraints_violated` list, and
    `partial_result` (lowest-cost subset found + its projected score)
  - Never relax the fabrication constraint
  - Update `edit_cost` on each `ProposedEdit` record after optimization
  - _Requirements: 6.1–6.7_

  - [ ] 11.1 Implement optimizer with BoundedSubsetSearch, cost formula, and minimality
    - Integrate with `POST /api/recourse/generate` pipeline
    - _Requirements: 6.1–6.7_

  - [ ]* 11.2 Property test — edit cost formula correctness (Property 14)
    - `Feature: verifiable-counterfactual-recourse, Property 14`
    - Generate arbitrary (levenshtein, statements_ratio, sbert_cosine, sections_ratio);
      compute expected cost manually; assert stored `edit_cost` equals expected within 1e-9
    - **Validates: Requirements 6.2**

  - [ ]* 11.3 Property test — optimizer structural invariants (Property 15)
    - `Feature: verifiable-counterfactual-recourse, Property 15`
    - For any feasible result: assert revised resume contains all original named sections;
      contact block unchanged; all CandidateFact claim texts present
    - **Validates: Requirements 6.3**

  - [ ]* 11.4 Unit tests — optimizer
    - Test cost formula with known inputs matches expected value within 1e-9
    - Test minimality: a smaller feasible subset is preferred over a larger one
    - Test infeasible result includes non-empty `constraints_violated` and `partial_result`
    - Test fabrication constraint is never relaxed
    - Test `verify_structure` fails when a named section is removed
    - _Requirements: 6.1–6.7_

---

### Vaishnavi — Verifier + Explanation Service

- [ ] 12. Evidence verifier
  - **Owner: Vaishnavi** · Branch: `vaishnavi/verifier`
  - Implement `backend/app/services/verifier.py`:
    - `verify_edit(edit, facts, llm_config) → VerificationReport`
  - Verification steps in strict order:
    1. `check_span_overlap(proposed_text, fact.source_span)` → `source_span_match`
    2. spaCy NER on `proposed_text` → `entities_in_proposed`
    3. spaCy NER on each referenced fact → `entities_in_evidence`
    4. `new_entities = entities_in_proposed − entities_in_evidence`
    5. Cross-encoder NLI: `predict(premise=fact.claim_text, hypothesis=proposed_text)`
       → `entailment_score` clamped to [0.0, 1.0]
    6. Apply decision rules in priority order:
       - **(d)** new entity detected → `Unsupported` (checked first, always)
       - **(a)** span match + entailment ≥ 0.5 + no new entity → `Supported`
       - **(b)** span match + (entailment < 0.5 or minor related entity) → `Partially Supported`
       - **(c)** no span match + entailment ≥ 0.5 + no new entity → `Needs Confirmation`
    7. LLM advisory (if `llm_config.enabled`): may only upgrade `Unsupported → Needs Confirmation`;
       cannot produce `Supported` or `Partially Supported`
  - `VerificationReport` fields: `edit_id`, `methods_used`, `evidence_fact_ids`,
    `assigned_status`, `entailment_score`, `rationale`
  - Every submitted `ProposedEdit` must receive exactly one `VerificationReport`
  - Trigger re-optimization when any edit receives `Unsupported` (Req 7.6)
  - Wire `POST /api/recourse/{id}/verify`; return 404 if recourse_id not found
  - _Requirements: 7.1–7.8_

  - [ ] 12.1 Implement verifier with 4 decision rules, NLI, and LLM advisory
    - _Requirements: 7.1–7.8_

  - [ ]* 12.2 Property test — entailment score bounds (Property 16)
    - `Feature: verifiable-counterfactual-recourse, Property 16`
    - For any (premise, hypothesis) pair, assert `entailment_score` ∈ [0.0, 1.0]
    - **Validates: Requirements 7.2**

  - [ ]* 12.3 Property test — decision rule correctness (Property 17)
    - `Feature: verifiable-counterfactual-recourse, Property 17`
    - Generate arbitrary (source_span_match, entailment_score, new_entities, minor_entity)
      combinations; assert assigned status follows the four rules in strict priority order
    - **Validates: Requirements 7.4**

  - [ ]* 12.4 Property test — LLM advisory cannot produce Supported (Property 18)
    - `Feature: verifiable-counterfactual-recourse, Property 18`
    - Generate inputs where LLM advisory is the only positive signal (no span match,
      entailment < 0.5); assert status is never `"Supported"` or `"Partially Supported"`
    - **Validates: Requirements 7.3**

  - [ ]* 12.5 Property test — verification completeness (Property 19)
    - `Feature: verifiable-counterfactual-recourse, Property 19`
    - Submit batches of N ProposedEdits; assert exactly N VerificationReports returned
    - **Validates: Requirements 7.8**

  - [ ]* 12.6 Unit tests — verifier
    - Test all 4 decision rule branches with crafted (span, entailment, entities) inputs
    - Test LLM advisory: `Unsupported → Needs Confirmation` allowed; `→ Supported` forbidden
    - Test `methods_used` records each method consulted
    - Test `rationale` is non-empty for every report
    - Test 404 on unknown recourse_id
    - _Requirements: 7.1–7.8_

---

- [ ] 13. Explanation service
  - **Owner: Vaishnavi** · Branch: `vaishnavi/explanation-service`
  - Implement `backend/app/services/explanation_service.py`:
    - `build_card(edit, facts, requirements) → ExplanationCard`
    - `build_aggregate(accepted_edits) → AggregateMetrics`
  - `ExplanationCard` must include all 7 required fields (Req 8.1):
    prose description, reason for ATS improvement, evidence fact IDs + claim texts,
    JR IDs + requirement texts, `score_contribution`, `edit_cost`, `verification_status`
  - `AggregateMetrics`: total edit cost, projected final score, projected decision,
    overall grounding rate, unsupported-claim rate (Req 8.3)
  - Confirm action: set `verification_status = "Supported"` on a `Needs Confirmation` edit
  - Reject action: set `verification_status = "Unsupported"` on a `Needs Confirmation` edit;
    do NOT trigger regeneration on reject
  - Expose confirm/reject via `PATCH /api/recourse/edits/{edit_id}/status`
  - _Requirements: 8.1–8.6_

  - [ ] 13.1 Implement explanation service with cards, aggregate metrics, and confirm/reject
    - _Requirements: 8.1–8.6_

  - [ ]* 13.2 Property test — explanation card completeness (Property 20)
    - `Feature: verifiable-counterfactual-recourse, Property 20`
    - For any accepted ProposedEdit, assert ExplanationCard contains all 7 required
      fields and none are null
    - **Validates: Requirements 8.1, 8.2**

  - [ ]* 13.3 Property test — confirm/reject status transitions (Property 21)
    - `Feature: verifiable-counterfactual-recourse, Property 21`
    - For any `Needs Confirmation` edit: after Confirm assert status == `"Supported"`;
      after Reject assert status == `"Unsupported"`
    - **Validates: Requirements 8.5, 8.6**

  - [ ]* 13.4 Unit tests — explanation service
    - Test all 7 card fields present and non-null for a mocked accepted edit
    - Test `Needs Confirmation` card includes Confirm and Reject controls in response
    - Test aggregate metrics computed correctly
    - Test Reject does not trigger recourse regeneration
    - _Requirements: 8.1–8.6_

---

## Milestone 4 — Frontend + Export (Parallel after Milestone 3)

> **Yash** and **Shahin** work solo in parallel after Milestone 3 is merged.

---

### Yash — Frontend Setup + 4 Screens + API Integration Tests

- [ ] 14. Frontend project setup and routing
  - **Owner: Yash** · Branch: `yash/frontend-setup`
  - Initialise `frontend/` with Vite + React 18 + TypeScript strict mode
  - Install pinned deps: `react@18.3.1`, `react-router-dom@6.23.1`,
    `@tanstack/react-query@5.36.2`, `recharts@2.12.7`, `diff-match-patch@1.0.5`,
    `msw@2.3.1`, `vitest@1.6.0`, `@testing-library/react@16.0.0`
  - Implement `queryKeys` factory (per design)
  - Implement `SessionGuard` HOC: reads `activeSession` from React context backed by
    `localStorage`; if `resumeId` or `jobDescriptionId` missing, redirect to
    `/input?redirect=<original>` with message "Please upload a resume and job description first"
  - Configure React Router with all 7 routes: `/`, `/input`, `/evidence`, `/analysis`,
    `/recommendations`, `/comparison`, `/research`
  - Implement global `<LoadingSpinner />` and `<ErrorBanner message onRetry />` components
  - Set up `msw` handlers for all API endpoints for test isolation
  - _Requirements: 12.1, 12.8, 12.9_

  - [ ] 14.1 Bootstrap frontend with Vite, routing, session guard, TanStack Query, and msw
    - Verify `vitest run` passes with 0 failures
    - _Requirements: 12.1, 12.8, 12.9_

  - [ ]* 14.2 Vitest tests — session guard redirects
    - Test navigate to `/evidence` without session → redirect to `/input` with message
    - Test same for `/analysis`, `/recommendations`, `/comparison`
    - _Requirements: 12.9_

---

- [ ] 15. Resume & JD input screen + evidence review screen + ATS analysis screen
  - **Owner: Yash** · Branch: `yash/frontend-screens-1`
  - Implement `ResumeJDInputScreen` (`/input`):
    - File upload (PDF/DOCX, max 10 MB shown in UI) or manual text area (max 50,000 chars)
    - JD text input (max 10,000 chars)
    - Loading indicator while submission in-flight (Req 12.3)
    - `useMutation` for `POST /api/resumes/upload` / `POST /api/resumes/manual`
    - `useMutation` for `POST /api/job-descriptions`
  - Implement `CandidateEvidenceReviewScreen` (`/evidence`):
    - `useQuery` for `GET /api/candidates/{id}/evidence`
    - Display `claim_text`, `claim_type`, `verification_status`, `original_claim_text`
    - Inline edit: update `claim_text` and `verification_status` via `useMutation` (Req 12.4)
  - Implement `ATSAnalysisScreen` (`/analysis`):
    - `useQuery` for score breakdown
    - Display total score, sub-scores, weights, threshold, and ATS disclosure (Req 12.5)
  - _Requirements: 12.2, 12.3, 12.4, 12.5_

  - [ ] 15.1 Implement input, evidence review, and ATS analysis screens
    - _Requirements: 12.2–12.5_

  - [ ]* 15.2 Vitest component tests — screens 1–3
    - Test file upload form: renders, validates size limit, shows loading spinner
    - Test evidence review: renders `claim_text` + `original_claim_text`; PATCH mutation fires on edit
    - Test analysis screen: renders score breakdown and disclosure statement
    - _Requirements: 12.3, 12.4, 12.5_

---

- [ ] 16. Counterfactual recommendations screen
  - **Owner: Yash** · Branch: `yash/frontend-recommendations`
  - Implement `CounterfactualRecommendationsScreen` (`/recommendations`):
    - One `ExplanationCard` per accepted `ProposedEdit` with all 7 required fields
    - `Needs Confirmation` cards: distinct label + yellow border/badge + Confirm/Reject controls
    - Aggregate metrics panel: total edit cost, projected score, decision, grounding rate,
      unsupported rate (Req 8.3)
    - Individual edit reject: exclude from accepted set without triggering regeneration (Req 12.6)
  - _Requirements: 8.2, 8.3, 8.4, 12.6_

  - [ ] 16.1 Implement counterfactual recommendations screen
    - _Requirements: 8.2, 8.3, 8.4, 12.6_

  - [ ]* 16.2 Vitest component tests — recommendations screen
    - Test ExplanationCard renders all 7 required fields
    - Test `Needs Confirmation` card shows yellow indicator and Confirm/Reject buttons
    - Test individual reject excludes edit without re-fetching
    - _Requirements: 8.2–8.4, 12.6_

---

- [ ] 17. Backend API integration tests
  - **Owner: Yash** · Branch: `yash/api-integration-tests`
  - Implement `tests/integration/test_api_resumes.py`:
    - Full upload round-trip (PDF fixture, DOCX fixture, manual text)
    - Error paths: 413, 415, 422 empty extraction
    - `GET /api/resumes/{id}` 404
  - Implement `tests/integration/test_api_analysis.py`:
    - Scoring request lifecycle; `ResumeVersion` v1 created
    - 404 on invalid `resume_id` and `job_description_id`
    - 502 on mocked SBERT failure
  - Implement `tests/integration/test_api_recourse.py`:
    - Generate → verify → accept lifecycle (feasible path)
    - Generate → infeasible path with `partial_result` shape
    - Confirm/Reject flow for `Needs Confirmation` edit
  - Implement `tests/integration/test_api_experiments.py`:
    - `ExperimentRun` CRUD, paginated list, filter AND semantics
  - Implement `tests/integration/test_db_constraints.py`:
    - FK cascade delete, enum constraint, UNIQUE conflict, AppendOnly enforcement
  - _Requirements: 13.1, 14.1–14.7_

  - [ ] 17.1 Implement all 5 backend integration test suites
    - _Requirements: 13.1, 14.1–14.7_

---

### Shahin — Export Service + Final Comparison Screen + Research Dashboard + E2E Tests

- [ ] 18. Export service
  - **Owner: Shahin** · Branch: `shahin/export-service`
  - Implement `backend/app/services/export_service.py`:
    - `apply_edits(base_version: ResumeVersion, accepted_edits: list[ProposedEdit]) → ResumeVersion`
    - `export_txt(version: ResumeVersion) → bytes`
    - `export_pdf(version: ResumeVersion) → bytes` (using `reportlab`)
  - New `ResumeVersion` must have `version_number = max_existing + 1`
  - Never modify the original `ResumeDocument` or `ResumeVersion(version_number=1)`
  - On file serialization failure: return `{error: {code, message}}` and create no partial record
  - Record accepted `ResumeVersion.id`, `ats_score`, `decision` in `ExperimentRun`;
    create run if none exists for the session
  - Wire `POST /api/recourse/{id}/accept` and `GET /api/resumes/versions/{id}/download`
  - _Requirements: 9.1–9.6_

  - [ ] 18.1 Implement export service with apply_edits, txt, and PDF export
    - _Requirements: 9.1–9.6_

  - [ ]* 18.2 Property test — original resume immutability (Property 22)
    - `Feature: verifiable-counterfactual-recourse, Property 22`
    - For any acceptance operation, assert `ResumeDocument` record and
      `ResumeVersion(version_number=1)` content are byte-for-byte unchanged
    - **Validates: Requirements 9.2**

  - [ ]* 18.3 Unit tests — export service
    - Test new `ResumeVersion` has `version_number = prior_max + 1`
    - Test original `ResumeDocument` and baseline version unchanged after export
    - Test export failure returns structured error with no partial record created
    - Test `.txt` and `.pdf` paths each return non-empty bytes
    - _Requirements: 9.1–9.6_

---

- [ ] 19. Final resume comparison screen
  - **Owner: Shahin** · Branch: `shahin/frontend-comparison`
  - Implement `FinalResumeComparisonScreen` (`/comparison`):
    - Side-by-side diff using `diff-match-patch`; split on `/(?<=[.!?])\s+/`;
      additions highlighted green, deletions struck through (Req 12.7, 9.3)
    - Download controls for `.txt` and PDF (Req 9.4)
    - Calls `GET /api/resumes/versions/{id}/download?format=txt|pdf`
  - _Requirements: 9.3, 9.4, 12.7_

  - [ ] 19.1 Implement final resume comparison screen with diff view and download controls
    - _Requirements: 9.3, 9.4, 12.7_

  - [ ]* 19.2 Vitest component tests — comparison screen
    - Test diff view: additions highlighted, deletions struck through
    - Test download button fires correct API call for both formats
    - _Requirements: 9.3, 9.4, 12.7_

---

- [ ] 20. Research evaluation dashboard
  - **Owner: Shahin** · Branch: `shahin/research-dashboard`
  - Implement backend `GET /api/experiments` route (if not already wired by Vipul in Task 24):
    - Pagination: `page`, `page_size=20`
    - Filters: `baseline_method`, `start_date`, `end_date`, `threshold`, `model_name`
    - AND filter semantics; zero-results → message not error
    - Returns 6 summary fields per item: `id`, `baseline_method`, `original_score`,
      `final_score`, `decision_flipped`, `created_at`
  - Implement `ResearchEvaluationDashboardScreen` (`/research`):
    - `ExperimentFilters` controls (baseline method, date range, threshold, model name)
    - `AggregateMetricsPanel`: flip rate (decision_flipped / total), run count,
      mean edit cost, mean grounding rate, mean unsupported rate, mean fact preservation
    - `MethodComparisonChart`: Recharts `<BarChart>` with 3 grouped bars (original_resume,
      generic_llm, proposed) × 5 metrics
    - `RunDetailTable`: paginated list with links to `GET /api/experiments/{id}/report`
  - _Requirements: 11.1–11.6, 12.1_

  - [ ] 20.1 Implement research dashboard screen and GET /api/experiments with AND filter semantics
    - _Requirements: 11.1–11.6_

  - [ ]* 20.2 Property test — experiment list filter AND semantics (Property 26)
    - `Feature: verifiable-counterfactual-recourse, Property 26`
    - Generate arbitrary filter combinations; for every returned item assert it satisfies
      ALL active filter conditions simultaneously
    - **Validates: Requirements 11.2**

  - [ ]* 20.3 Property test — GET /api/experiments summary field completeness (Property 27)
    - `Feature: verifiable-counterfactual-recourse, Property 27`
    - For any page of results, assert every item contains exactly the 6 required
      summary fields
    - **Validates: Requirements 11.6**

  - [ ]* 20.4 Vitest tests — research dashboard
    - Test chart renders 3 grouped bar sets for 3 baseline methods
    - Test filter form fires API call with correct params
    - Test zero-results state shows message, not error
    - Test RunDetailTable links to correct report URL
    - _Requirements: 11.1–11.6_

---

- [ ] 21. End-to-end tests
  - **Owner: Shahin** · Branch: `shahin/e2e-tests`
  - Implement `tests/e2e/test_full_workflow.py` — complete happy path (11 steps):
    1. `POST /api/resumes/upload` (PDF fixture) → `ResumeDocument` created
    2. `GET /api/resumes/{id}` → extracted text non-empty, source spans valid
    3. `GET /api/candidates/{id}/evidence` → all facts `Needs Confirmation`
    4. `PATCH` one fact to `Supported`
    5. `POST /api/job-descriptions` → `JobRequirement`s extracted
    6. `POST /api/analysis` → `ResumeVersion` v1, decision `fail`
    7. `POST /api/recourse/generate` → `ProposedEdit`s with valid cost
    8. `POST /api/recourse/{id}/verify` → `VerificationReport` for every edit
    9. `POST /api/recourse/{id}/accept` → `ResumeVersion` v2 created, `ExperimentRun` created
    10. `GET /api/resumes/versions/{id}/download?format=txt` → non-empty bytes
    11. `GET /api/experiments/{run_id}` → full `ExperimentRun` with all 13 fields
  - Implement `tests/e2e/test_infeasible_workflow.py`:
    - All facts set to `Unsupported` → `generate` returns `infeasible` with `all_unsupported`
    - Assert `constraints_violated` and `partial_result` fields present
  - Implement `tests/e2e/test_research_dashboard.py`:
    - Create 3 runs with different `baseline_method` values
    - `GET /api/experiments?baseline_method=proposed` → only proposed runs returned
    - Assert all 6 summary fields present per item
  - _Requirements: all_

  - [ ] 21.1 Implement happy-path, infeasible-path, and dashboard E2E test suites
    - _Requirements: all_

---

## Milestone 5 — Experiment Logger + Research CLI

> **Vipul** (experiment logger) and **Varun** (research CLI + final integration)
> work in parallel after Milestone 4 is merged.

---

### Vipul — Experiment Logger

- [ ] 22. Experiment logger
  - **Owner: Vipul** · Branch: `vipul/experiment-logger`
  - Implement `backend/app/services/experiment_logger.py`:
    - `create_run(payload: ExperimentRunCreate) → ExperimentRun`
    - `get_run(run_id: UUID) → ExperimentRun`
    - `list_runs(filters, page, page_size) → PaginatedResult[ExperimentRunSummary]`
    - `get_report(run_id: UUID) → ExperimentReport`
  - Validate all 13 required fields present on create
  - Validate `grounding_metrics` rates ∈ [0.0, 1.0]
  - Validate `baseline_method` ∈ `{original_resume, generic_llm, proposed}`; return 422 otherwise
  - Record ALL generated `ProposedEdit`s (including rejected) via `experiment_run_edits` junction
  - Enforce append-only via `AppendOnlyMixin`; return 409 on mutation attempt
  - Wire `POST /api/experiments`, `GET /api/experiments/{id}`, `GET /api/experiments/{id}/report`
  - _Requirements: 10.1–10.8_

  - [ ] 22.1 Implement experiment logger with append-only enforcement and all routes
    - _Requirements: 10.1–10.8_

  - [ ]* 22.2 Property test — ExperimentRun field completeness and rate bounds (Property 23)
    - `Feature: verifiable-counterfactual-recourse, Property 23`
    - Generate arbitrary valid `ExperimentRunCreate` payloads; assert all 13 fields
      are non-null; assert all three grounding rates ∈ [0.0, 1.0]
    - **Validates: Requirements 10.1, 10.5**

  - [ ]* 22.3 Property test — ExperimentRun append-only immutability (Property 24)
    - `Feature: verifiable-counterfactual-recourse, Property 24`
    - After creating an `ExperimentRun`, attempt to update any field via service layer;
      assert `ImmutableRecordError` is always raised
    - **Validates: Requirements 10.8**

  - [ ]* 22.4 Unit tests — experiment logger
    - Test all 13 fields present on created run
    - Test `baseline_method` outside enum returns 422
    - Test `grounding_metrics` rates validated ∈ [0.0, 1.0]
    - Test append-only: `ImmutableRecordError` raised on mutation
    - Test `list_runs` pagination returns correct `total`, `page`, `page_size`
    - Test `get_report` returns all `ProposedEdit`s including rejected ones
    - _Requirements: 10.1–10.8_

---

### Varun — Research CLI + Final Integration

- [ ] 23. Research CLI
  - **Owner: Varun** · Branch: `varun/research-cli`
  - Implement `research_cli.py` with two subcommands:
    - `run --config <yaml> --resume <path> --jd <path> --baseline <method> --seed <int>`:
      reads YAML config, runs full pipeline via service layer, records via `Experiment_Logger`
    - `compare --run-ids <uuid...> --output <path>`: retrieves runs and writes comparison JSON
  - YAML config structure (per design): `experiment_id`, `baseline_method`, `random_seed`,
    `model_configuration` with all scoring and optimization fields
  - CLI must record results identically to the web path (same `Experiment_Logger.create_run()`)
  - _Requirements: 10.1–10.3, 10.6_

  - [ ] 23.1 Implement research CLI with run and compare subcommands
    - Test `run` subcommand produces an `ExperimentRun` record in DB with correct fields
    - Test `compare` subcommand writes valid JSON output
    - _Requirements: 10.1–10.3, 10.6_

---

- [ ] 24. Final integration
  - **Owner: Varun** · Branch: `varun/final-integration`
  - Pull all merged modules from `integration`; verify the full test suite passes:
    - `pytest tests/ --cov=app --cov-report=term` (backend)
    - `vitest run --coverage` (frontend)
  - Run research CLI end-to-end: `python research_cli.py run --config experiments/config_001.yaml ...`
    and confirm `ExperimentRun` record created
  - Verify Research Dashboard loads and displays grouped bar charts for all 3 baseline methods
  - Confirm full happy-path E2E test (`test_full_workflow.py`) passes
  - Confirm infeasible-path E2E test (`test_infeasible_workflow.py`) passes
  - Merge `integration` → `main`
  - _Requirements: all_

  - [ ] 24.1 Run full test suite, verify all E2E paths, merge integration → main
    - _Requirements: all_

---

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": 0,
      "label": "Milestone 1 — Foundation (Varun solo)",
      "tasks": ["1.1", "2.1", "3.1", "4.1"]
    },
    {
      "id": 1,
      "label": "Milestone 1 optional property/unit tests (Varun)",
      "tasks": ["1.2", "2.2"]
    },
    {
      "id": 2,
      "label": "Milestone 2 — Backend services in parallel (Vipul, Dhruv, Vaishnavi)",
      "tasks": ["5.1", "6.1", "7.1", "8.1", "9.1"]
    },
    {
      "id": 3,
      "label": "Milestone 2 optional tests",
      "tasks": ["5.2", "5.3", "5.4", "5.5", "6.2", "6.3", "7.2", "7.3", "7.4", "8.2", "8.3", "9.2", "9.3", "9.4", "9.5"]
    },
    {
      "id": 4,
      "label": "Milestone 3 — Core research (Varun + Vaishnavi in parallel)",
      "tasks": ["10.1", "11.1", "12.1", "13.1"]
    },
    {
      "id": 5,
      "label": "Milestone 3 optional tests",
      "tasks": ["10.2", "10.3", "10.4", "10.5", "11.2", "11.3", "11.4", "12.2", "12.3", "12.4", "12.5", "12.6", "13.2", "13.3", "13.4"]
    },
    {
      "id": 6,
      "label": "Milestone 4 — Frontend + Export (Yash + Shahin in parallel)",
      "tasks": ["14.1", "15.1", "16.1", "17.1", "18.1", "19.1", "20.1", "21.1"]
    },
    {
      "id": 7,
      "label": "Milestone 4 optional tests",
      "tasks": ["14.2", "15.2", "16.2", "18.2", "18.3", "19.2", "20.2", "20.3", "20.4"]
    },
    {
      "id": 8,
      "label": "Milestone 5 — Experiment Logger + CLI (Vipul + Varun in parallel)",
      "tasks": ["22.1", "23.1"]
    },
    {
      "id": 9,
      "label": "Milestone 5 optional tests",
      "tasks": ["22.2", "22.3", "22.4"]
    },
    {
      "id": 10,
      "label": "Final Integration (Varun)",
      "tasks": ["24.1"]
    }
  ]
}
```

---

## Notes

- Tasks marked `*` are optional and can be skipped for a faster MVP
- Property-based tests use `hypothesis` with `@settings(max_examples=100)` minimum
- Each property test must include the comment:
  `Feature: verifiable-counterfactual-recourse, Property {N}: {property_text}`
- All branches target `integration`; only **Varun** merges
- Milestone gates: Varun reviews and merges each milestone before the next begins
