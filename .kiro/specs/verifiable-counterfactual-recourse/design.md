# Design Document — Verifiable Counterfactual Recourse for Resume–ATS Rejection

## Overview

This system is a research-oriented full-stack application that identifies the smallest
truthful, evidence-supported changes a candidate can make to their resume to cross a
configurable simulated ATS screening threshold. The primary research contribution is
demonstrating that *truth-constrained minimal-edit counterfactual recommendations*
achieve a comparable decision-flip rate to generic LLM suggestions while producing
fewer unsupported claims and requiring smaller edits.

### Design Philosophy

The system is implemented as a **modular monolith**: a single deployable backend process
with clearly bounded internal services, each owning its own data access layer and
business logic. Module boundaries are enforced via Python packages; inter-module
communication happens through well-typed Python function calls and shared SQLAlchemy
session management — not HTTP. This approach enables clean separation of concerns and
simple local development while avoiding the operational overhead of a microservices
architecture for a research prototype.

The frontend is a single-page application (React + Vite + TypeScript) that communicates
exclusively through the FastAPI REST layer.

### Technology Choices

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | React 18, Vite, TypeScript, TanStack Query, Recharts | SPA for fluent multi-step workflow; TanStack Query for server-state caching |
| API | FastAPI, Pydantic v2 | Automatic OpenAPI generation, Pydantic validation, async support |
| ORM / Migrations | SQLAlchemy 2.x, Alembic | Declarative models, type-safe queries, migration-as-code |
| Database | PostgreSQL 15 | JSONB for flexible metadata, enum types, robust FK enforcement |
| NLP — Embeddings | `sentence-transformers` (all-MiniLM-L6-v2 default) | SBERT cosine similarity for ATS scoring and rephrase validation |
| NLP — Extraction | `spaCy` (en_core_web_trf default) | NER, skill extraction, entity consistency checks |
| Document Parsing | `PyMuPDF` (PDF), `python-docx` (DOCX) | Established libraries with character-level span support |
| OCR | `pytesseract` + Pillow | Fallback for scanned PDFs with no selectable text layer |
| Optimization | Custom bounded subset search (pure Python) | Deterministic, fully auditable, no external solver dependency |
| Entailment | `transformers` cross-encoder (cross-encoder/nli-MiniLM2-L6-H768) | Local NLI model; no API calls required |

---

## Architecture

### System Context Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Browser (SPA)                               │
│  React + Vite + TypeScript + TanStack Query + Recharts              │
│  Routes: / | /input | /evidence | /analysis |                       │
│          /recommendations | /comparison | /research                  │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTPS / JSON
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                             │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      Router Layer                            │   │
│  │  /api/resumes  /api/job-descriptions  /api/candidates        │   │
│  │  /api/analysis  /api/recourse  /api/experiments              │   │
│  └────────────────────────┬─────────────────────────────────────┘   │
│                           │                                         │
│  ┌────────────┐  ┌────────┴────────┐  ┌──────────────────────────┐ │
│  │ Ingestion  │  │  JD_Analyzer    │  │    Evidence_Extractor    │ │
│  │ _Service   │  │                 │  │    + Evidence_Bank       │ │
│  └────────────┘  └─────────────────┘  └──────────────────────────┘ │
│  ┌────────────┐  ┌─────────────────┐  ┌──────────────────────────┐ │
│  │ ATS_Scorer │  │ Recourse_Engine │  │       Optimizer          │ │
│  └────────────┘  └─────────────────┘  └──────────────────────────┘ │
│  ┌────────────┐  ┌─────────────────┐  ┌──────────────────────────┐ │
│  │  Verifier  │  │ Explanation_Svc │  │      Export_Service      │ │
│  └────────────┘  └─────────────────┘  └──────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │            Experiment_Logger                                   │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ SQLAlchemy / psycopg2
                              ▼
                    ┌──────────────────┐
                    │   PostgreSQL 15  │
                    └──────────────────┘
```

### Module Dependency Graph (Build Order)

```
shared_models (SQLAlchemy ORM, Pydantic schemas, enums)
      │
      ├─► Ingestion_Service ──► Evidence_Extractor ──► Evidence_Bank
      │
      ├─► JD_Analyzer
      │
      ├─► ATS_Scorer (depends on: Ingestion, JD_Analyzer, Evidence_Bank)
      │
      ├─► Recourse_Engine (depends on: ATS_Scorer, Evidence_Bank)
      │         │
      │         └─► Optimizer (depends on: ATS_Scorer, Recourse_Engine)
      │
      ├─► Verifier (depends on: Evidence_Bank, Recourse_Engine)
      │
      ├─► Explanation_Service (depends on: Verifier, Recourse_Engine)
      │
      ├─► Export_Service (depends on: Explanation_Service)
      │
      └─► Experiment_Logger (depends on: all above)
```

### Data Flow — Happy Path

```
Upload PDF/DOCX  ──►  Ingestion_Service  ──►  ResumeDocument + source spans
                                         ──►  Evidence_Extractor  ──►  CandidateFact[]
Submit JD        ──►  JD_Analyzer        ──►  JobRequirement[]
Candidate reviews evidence (PATCH /api/candidates/{id}/evidence/{fact_id})
POST /api/analysis ──►  ATS_Scorer  ──►  ResumeVersion (v1, baseline score)
POST /api/recourse/generate  ──►  Recourse_Engine  ──►  ProposedEdit[]
                             ──►  Optimizer         ──►  minimal-cost feasible subset
POST /api/recourse/{id}/verify ──►  Verifier  ──►  verification_status per edit
Candidate reviews  ──►  Explanation_Service  ──►  explanation cards + aggregate metrics
POST /api/recourse/{id}/accept ──►  Export_Service ──►  ResumeVersion (v2+)
                               ──►  Experiment_Logger ──►  ExperimentRun (append-only)
```

---

## Components and Interfaces

### Ingestion_Service

**Responsibility**: Accept file uploads or manual text; produce `ResumeDocument` records with
character-level source spans.

**Key Interfaces**:
```python
class IngestionService:
    def ingest_file(self, file: UploadFile, candidate_id: UUID) -> ResumeDocument: ...
    def ingest_manual(self, text: str, candidate_id: UUID) -> ResumeDocument: ...
    def get_resume(self, resume_id: UUID) -> ResumeDocument: ...

class SourceSpan(BaseModel):
    start: int  # inclusive char offset
    end: int    # exclusive char offset

class ExtractedSegment(BaseModel):
    text: str
    span: SourceSpan
```

**Processing Logic**:
1. Check file size (> 10 MB → HTTP 413)
2. Check MIME/extension (not PDF/DOCX → HTTP 415)
3. Dispatch by type: DOCX → python-docx, PDF → PyMuPDF
4. If PyMuPDF returns zero non-whitespace chars → fall back to pytesseract OCR
5. Build `ExtractedSegment` list with cumulative char offsets
6. Persist `ResumeDocument`

**File Storage Abstraction**: A `StorageBackend` protocol with two implementations:
- `LocalFileStorage` — writes to configurable `UPLOAD_DIR` on disk (default for dev)
- `S3CompatibleStorage` — writes to any S3-compatible endpoint (configurable via env vars)

---

### JD_Analyzer

**Responsibility**: Parse a raw job description string; produce `JobRequirement` records with
normalized skill names, importance labels, explicit/inferred distinction, and source spans.

**Key Interfaces**:
```python
class JDAnalyzer:
    def analyze(self, jd_text: str) -> tuple[JobDescriptionRecord, list[JobRequirement]]: ...
    def get_jd(self, jd_id: UUID) -> JobDescriptionRecord: ...
```

**Processing Logic**:
1. spaCy NLP pipeline: NER pass, dependency parsing for signal word detection
2. Signal word mapping: `{"must have", "required", "must"} → "required"`,
   `{"preferred", "nice to have", "desired", "plus"} → "preferred"`, default → `"required"`
3. Skill canonicalization via hardcoded normalization map + spaCy entity linking
4. Mark each requirement as `explicit` (direct phrase) or `inferred` (derived by NLP)
5. Record `{start, end}` char offsets from spaCy token spans

---

### Evidence_Extractor + Evidence_Bank

**Responsibility**: `Evidence_Extractor` transforms a `ResumeDocument` into `CandidateFact`
records. `Evidence_Bank` manages the CRUD lifecycle and enforces the audit-trail invariants.

**Key Interfaces**:
```python
class EvidenceExtractor:
    def extract(self, resume: ResumeDocument) -> list[CandidateFact]: ...

class EvidenceBank:
    def get_facts(self, candidate_id: UUID) -> list[CandidateFact]: ...
    def update_fact(self, candidate_id: UUID, fact_id: UUID,
                    patch: CandidateFactPatch) -> CandidateFact: ...
    def get_usable_facts(self, candidate_id: UUID) -> list[CandidateFact]:
        """Returns facts with verification_status != Unsupported."""
```

**Claim Types Extracted**: `skill`, `project`, `responsibility`, `certification`,
`experience`, `achievement`

**Invariants**:
- `original_claim_text` is set once at creation and never mutated
- `claim_text` may be updated by the candidate; `updated_at` is stamped on each change
- Auto-extracted facts start with `verification_status = "Needs Confirmation"`

---

### ATS_Scorer

**Responsibility**: Produce a deterministic, configurable `[0.0, 1.0]` score from a resume
text + job description text pair using skill overlap and Sentence-BERT similarity.

**Key Interfaces**:
```python
class ATSScorer:
    def score(self, resume_text: str, jd_text: str,
              config: ScoringConfig) -> ScoreResult: ...

class ScoringConfig(BaseModel):
    skill_overlap_weight: float = 0.5   # must sum to 1.0 with sbert_weight
    sbert_weight: float = 0.5
    threshold: float = 0.5
    sbert_model_name: str = "all-MiniLM-L6-v2"

class ScoreResult(BaseModel):
    total_score: float
    skill_overlap_score: float
    semantic_similarity_score: float
    weights: dict[str, float]
    threshold: float
    decision: Literal["pass", "fail"]
```

**Determinism**: The SBERT model is loaded once at application startup and reused for all
requests. No sampling or stochastic components are involved. Given identical inputs, the
cosine similarity computation always returns the same float.

---

### Recourse_Engine

**Responsibility**: Generate `ProposedEdit` candidates grounded in the Evidence Bank,
respecting edit type constraints, rephrase similarity floor, and fabrication prohibition.

**Key Interfaces**:
```python
class RecourseEngine:
    def generate(self, resume_version: ResumeVersion,
                 jd_id: UUID,
                 usable_facts: list[CandidateFact],
                 requirements: list[JobRequirement]) -> RecourseResult: ...

class RecourseResult(BaseModel):
    edits: list[ProposedEdit]   # max 20
    status: Literal["ok", "infeasible"]
    infeasible_reason: str | None
    infeasible_detail: str | None
```

**Edit Type Logic**:
- `rephrase`: Synonym/style replacement; validated with SBERT similarity ≥ 0.85
- `surface_qualification`: Moves buried but valid fact to a more prominent position
- `reorder`: Changes the order of bullet points or sections
- `normalize_terminology`: Applies canonical skill name from JD normalization map
- `reorganize_sections`: Moves a section to a different part of the resume
- `remove_redundancy`: Removes a duplicate claim already captured by another

**Fabrication Guard**: After each candidate edit is drafted, `Evidence_Extractor` runs a
quick NER pass on `proposed_text`; any named entity not present in the Evidence Bank
causes that edit to be discarded.

---

### Optimizer

**Responsibility**: Select the minimum-cost feasible subset of `ProposedEdit` candidates
that crosses the ATS threshold while satisfying all four constraints.

**Key Interfaces**:
```python
class Optimizer:
    def optimize(self, edits: list[ProposedEdit],
                 resume: ResumeVersion,
                 config: OptimizationConfig) -> OptimizationResult: ...

class OptimizationConfig(BaseModel):
    levenshtein_weight: float = 0.25
    changed_statements_weight: float = 0.25
    semantic_change_weight: float = 0.25
    moved_sections_weight: float = 0.25
    threshold: float = 0.5

class OptimizationResult(BaseModel):
    status: Literal["feasible", "infeasible"]
    accepted_edits: list[ProposedEdit]
    total_edit_cost: float
    projected_score: float
    projected_decision: Literal["pass", "fail"]
    constraints_violated: list[str] | None
    partial_result: PartialResult | None
```

**Search Strategy**: See "Counterfactual Optimization Formulation" section below.

---

### Verifier

**Responsibility**: Assign a `VerificationStatus` to each `ProposedEdit` using the four
ordered decision rules.

**Key Interfaces**:
```python
class Verifier:
    def verify_edit(self, edit: ProposedEdit,
                    facts: list[CandidateFact],
                    llm_config: LLMConfig | None) -> VerificationReport: ...

class VerificationReport(BaseModel):
    edit_id: UUID
    methods_used: list[Literal["source_span_match","entity_check","entailment","llm_advisory"]]
    evidence_fact_ids: list[UUID]
    assigned_status: VerificationStatus
    entailment_score: float
    rationale: str
```

---

### Explanation_Service

**Responsibility**: Build human-readable explanation cards and aggregate metrics from
verified `ProposedEdit` records.

**Key Interfaces**:
```python
class ExplanationService:
    def build_card(self, edit: ProposedEdit,
                   facts: list[CandidateFact],
                   requirements: list[JobRequirement]) -> ExplanationCard: ...
    def build_aggregate(self, accepted_edits: list[ProposedEdit]) -> AggregateMetrics: ...
```

---

### Export_Service

**Responsibility**: Apply accepted edits to produce a new `ResumeVersion`; generate
downloadable `.txt` and PDF files.

**Key Interfaces**:
```python
class ExportService:
    def apply_edits(self, base_version: ResumeVersion,
                    accepted_edits: list[ProposedEdit]) -> ResumeVersion: ...
    def export_txt(self, version: ResumeVersion) -> bytes: ...
    def export_pdf(self, version: ResumeVersion) -> bytes: ...
```

PDF generation uses `reportlab` (pure-Python, no system dependency).

---

### Experiment_Logger

**Responsibility**: Create append-only `ExperimentRun` records with full reproducibility
metadata; expose experiment history.

**Key Interfaces**:
```python
class ExperimentLogger:
    def create_run(self, payload: ExperimentRunCreate) -> ExperimentRun: ...
    def get_run(self, run_id: UUID) -> ExperimentRun: ...
    def list_runs(self, filters: ExperimentFilters,
                  page: int, page_size: int) -> PaginatedResult[ExperimentRunSummary]: ...
    def get_report(self, run_id: UUID) -> ExperimentReport: ...
```

**Append-only enforcement**: No `UPDATE` statements are issued on `experiment_runs`.
The SQLAlchemy model uses `__setattr__` override and a custom `AppendOnlyMixin` that
raises `ImmutableRecordError` on any post-creation mutation attempt.

---

### Research_Dashboard (Frontend Module)

**Responsibility**: Render `/research` route with filtered experiment lists and Recharts
grouped bar charts comparing the three baseline methods.

**Key Components**:
- `ExperimentFilters` — controls for baseline_method, date range, threshold, model name
- `AggregateMetricsPanel` — flip rate, run count, mean edit cost, mean grounding rate, etc.
- `MethodComparisonChart` — Recharts `BarChart` with grouped bars per baseline_method
- `RunDetailTable` — paginated list with links to `GET /api/experiments/{id}/report`

---

## Data Models

### Entity Relationship Overview

```
ResumeDocument ──< CandidateFact
ResumeDocument ──< ResumeVersion
ResumeVersion  ──< ProposedEdit
JobDescription ──< JobRequirement
ProposedEdit   >──< CandidateFact       (via proposed_edit_facts junction)
ProposedEdit   >──< JobRequirement      (via proposed_edit_requirements junction)
ExperimentRun  ──  ResumeDocument
ExperimentRun  ──  JobDescription
ExperimentRun  ──< ProposedEdit         (all edits, not just accepted)
```

---

### Table: `resume_documents`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID | PK | gen_random_uuid() |
| candidate_id | UUID | NOT NULL, INDEX | Application-level user id |
| filename | VARCHAR(255) | NULLABLE | NULL for manual entries |
| document_type | VARCHAR(10) | NOT NULL | CHECK IN ('pdf','docx','manual') |
| extracted_text | TEXT | NOT NULL | Full extracted content |
| source_spans | JSONB | NOT NULL | Array of {start,end,text} objects |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

---

### Table: `candidate_facts`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID | PK | |
| candidate_id | UUID | NOT NULL, INDEX | |
| claim_text | TEXT | NOT NULL, CHECK length ≤ 2000 | Current (editable) claim text |
| original_claim_text | TEXT | NOT NULL | Set at creation; never mutated |
| claim_type | VARCHAR(20) | NOT NULL | ENUM: skill, project, responsibility, certification, experience, achievement |
| source_document_id | UUID | NOT NULL, FK → resume_documents(id) ON DELETE CASCADE | |
| source_span | JSONB | NOT NULL | {start: int, end: int} |
| verification_status | verification_status_enum | NOT NULL DEFAULT 'Needs Confirmation' | DB enum enforced |
| metadata | JSONB | NOT NULL DEFAULT '{}' | Related fact associations |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | Updated on each PATCH |

**DB Enum**: `CREATE TYPE verification_status_enum AS ENUM ('Supported', 'Partially Supported', 'Unsupported', 'Needs Confirmation');`

---

### Table: `job_descriptions`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID | PK | |
| raw_text | TEXT | NOT NULL | Original submitted text |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

---

### Table: `job_requirements`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID | PK | |
| job_description_id | UUID | NOT NULL, FK → job_descriptions(id) ON DELETE CASCADE | |
| requirement_text | TEXT | NOT NULL | Extracted requirement text |
| requirement_type | VARCHAR(20) | NOT NULL | skill, certification, experience, qualification, responsibility |
| importance | VARCHAR(10) | NOT NULL DEFAULT 'required' | CHECK IN ('required','preferred') |
| extraction_type | VARCHAR(10) | NOT NULL | CHECK IN ('explicit','inferred') |
| normalized_skills | JSONB | NOT NULL DEFAULT '[]' | Array of canonical skill strings |
| source_span | JSONB | NOT NULL | {start: int, end: int} |

---

### Table: `resume_versions`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID | PK | |
| original_resume_id | UUID | NOT NULL, FK → resume_documents(id) | |
| version_number | INTEGER | NOT NULL | 1 = baseline; UNIQUE(original_resume_id, version_number) |
| content | TEXT | NOT NULL | Full text of this version |
| ats_score | FLOAT | NULLABLE | NULL until scored |
| decision | VARCHAR(4) | NULLABLE | CHECK IN ('pass','fail') |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

---

### Table: `proposed_edits`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID | PK | |
| resume_version_id | UUID | NOT NULL, FK → resume_versions(id) | |
| original_text | TEXT | NOT NULL | Text before edit |
| proposed_text | TEXT | NOT NULL | Text after edit |
| edit_type | VARCHAR(30) | NOT NULL | ENUM: rephrase, surface_qualification, reorder, normalize_terminology, reorganize_sections, remove_redundancy |
| verification_status | verification_status_enum | NOT NULL DEFAULT 'Needs Confirmation' | |
| edit_cost | FLOAT | NOT NULL | [0.0, 1.0] composite cost |
| score_contribution | FLOAT | NOT NULL | Estimated ATS score delta |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Junction Tables**:
- `proposed_edit_facts(proposed_edit_id UUID FK, candidate_fact_id UUID FK)` — PK(both cols)
- `proposed_edit_requirements(proposed_edit_id UUID FK, job_requirement_id UUID FK)` — PK(both cols)

---

### Table: `experiment_runs`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | UUID | PK | |
| resume_id | UUID | NOT NULL, FK → resume_documents(id) | |
| job_description_id | UUID | NOT NULL, FK → job_descriptions(id) | |
| model_configuration | JSONB | NOT NULL | See structure below |
| baseline_method | VARCHAR(20) | NOT NULL | ENUM: original_resume, generic_llm, proposed |
| original_score | FLOAT | NOT NULL | |
| final_score | FLOAT | NOT NULL | Partial result score for infeasible runs |
| threshold | FLOAT | NOT NULL | |
| decision_flipped | BOOLEAN | NOT NULL | |
| total_edit_cost | FLOAT | NOT NULL | |
| grounding_metrics | JSONB | NOT NULL | See structure below |
| random_seed | INTEGER | NULLABLE | NULL if no stochastic component |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**`model_configuration` JSONB structure**:
```json
{
  "sbert_model": "all-MiniLM-L6-v2",
  "sbert_version": "1.0",
  "spacy_model": "en_core_web_trf",
  "spacy_version": "3.7.2",
  "ats_skill_weight": 0.5,
  "ats_sbert_weight": 0.5,
  "threshold": 0.5,
  "edit_cost_weights": {
    "levenshtein": 0.25,
    "changed_statements": 0.25,
    "semantic_change": 0.25,
    "moved_sections": 0.25
  }
}
```

**`grounding_metrics` JSONB structure**:
```json
{
  "evidence_grounding_rate": 0.85,
  "unsupported_claim_rate": 0.05,
  "original_fact_preservation_rate": 1.0
}
```

**Junction Table**:
- `experiment_run_edits(experiment_run_id UUID FK, proposed_edit_id UUID FK)` — records ALL
  edits generated (including rejected), not only accepted.

---

## API Contracts

All endpoints return JSON. Success responses use `{"data": ...}`; error responses use
`{"error": {"code": "...", "message": "..."}}`.

### Endpoint Reference

#### 1. `POST /api/resumes/upload`
Upload a PDF or DOCX file.

**Request**: multipart/form-data
- `file`: binary (required)
- `candidate_id`: UUID string (required)

**Response 201**:
```json
{
  "data": {
    "id": "uuid",
    "candidate_id": "uuid",
    "filename": "resume.pdf",
    "document_type": "pdf",
    "extracted_text": "...",
    "created_at": "2024-01-15T10:00:00Z"
  }
}
```

**Errors**: 413 (file too large), 415 (unsupported type), 422 (extraction failed)

---

#### 2. `POST /api/resumes/manual`
Submit resume text manually.

**Request**:
```json
{
  "candidate_id": "uuid",
  "text": "Full resume text here..."
}
```

**Response 201**: Same shape as upload response with `document_type: "manual"`, `filename: null`.

**Errors**: 422 (empty or > 50,000 chars)

---

#### 3. `GET /api/resumes/{id}`

**Response 200**:
```json
{
  "data": {
    "id": "uuid",
    "candidate_id": "uuid",
    "filename": "resume.pdf",
    "document_type": "pdf",
    "extracted_text": "...",
    "source_spans": [{"start": 0, "end": 120, "text": "..."}],
    "created_at": "2024-01-15T10:00:00Z"
  }
}
```

**Errors**: 404

---

#### 4. `POST /api/job-descriptions`

**Request**:
```json
{
  "text": "Job description text (1–10,000 chars)"
}
```

**Response 201**:
```json
{
  "data": {
    "id": "uuid",
    "raw_text": "...",
    "requirements": [
      {
        "id": "uuid",
        "requirement_text": "5+ years Python experience",
        "requirement_type": "experience",
        "importance": "required",
        "extraction_type": "explicit",
        "normalized_skills": ["Python"],
        "source_span": {"start": 42, "end": 70}
      }
    ],
    "warning": null,
    "created_at": "2024-01-15T10:00:00Z"
  }
}
```

`warning` is a non-null string when zero requirements are extracted.

**Errors**: 422 (empty/whitespace body)

---

#### 5. `GET /api/job-descriptions/{id}`

**Response 200**: Same shape as POST response (without `warning`).

**Errors**: 404

---

#### 6. `GET /api/candidates/{id}/evidence`

**Response 200**:
```json
{
  "data": {
    "candidate_id": "uuid",
    "facts": [
      {
        "id": "uuid",
        "claim_text": "Developed REST APIs with FastAPI",
        "original_claim_text": "Developed RESTful APIs",
        "claim_type": "skill",
        "source_document_id": "uuid",
        "source_span": {"start": 100, "end": 122},
        "verification_status": "Needs Confirmation",
        "metadata": {},
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z"
      }
    ]
  }
}
```

**Errors**: 404

---

#### 7. `PATCH /api/candidates/{id}/evidence/{fact_id}`

**Request** (all fields optional, at least one required):
```json
{
  "claim_text": "Updated claim (max 2000 chars)",
  "verification_status": "Supported"
}
```

**Response 200**:
```json
{
  "data": { /* updated CandidateFact */ }
}
```

**Errors**: 404, 422 (invalid status value / claim_text too long or empty)

---

#### 8. `POST /api/analysis`

**Request**:
```json
{
  "resume_id": "uuid",
  "job_description_id": "uuid",
  "scoring_config": {
    "skill_overlap_weight": 0.5,
    "sbert_weight": 0.5,
    "threshold": 0.5
  }
}
```

**Response 201**:
```json
{
  "data": {
    "resume_version_id": "uuid",
    "version_number": 1,
    "score_breakdown": {
      "total_score": 0.42,
      "skill_overlap_score": 0.38,
      "semantic_similarity_score": 0.46,
      "weights": {"skill_overlap": 0.5, "sbert": 0.5},
      "threshold": 0.5
    },
    "decision": "fail",
    "disclosure": "This score is produced by a simulated model and does not predict any employer's hiring decision."
  }
}
```

**Errors**: 404 (invalid resume_id or job_description_id), 422 (invalid weights), 502 (SBERT model failure)

---

#### 9. `POST /api/recourse/generate`

**Request**:
```json
{
  "resume_version_id": "uuid",
  "job_description_id": "uuid",
  "optimization_config": {
    "levenshtein_weight": 0.25,
    "changed_statements_weight": 0.25,
    "semantic_change_weight": 0.25,
    "moved_sections_weight": 0.25,
    "threshold": 0.5
  }
}
```

**Response 201 (feasible)**:
```json
{
  "data": {
    "recourse_id": "uuid",
    "status": "feasible",
    "accepted_edits": [
      {
        "id": "uuid",
        "original_text": "Worked on backend systems",
        "proposed_text": "Designed and maintained Python microservices",
        "edit_type": "rephrase",
        "evidence_fact_ids": ["uuid"],
        "job_requirement_ids": ["uuid"],
        "verification_status": "Needs Confirmation",
        "edit_cost": 0.18,
        "score_contribution": 0.06
      }
    ],
    "total_edit_cost": 0.18,
    "projected_score": 0.54,
    "projected_decision": "pass"
  }
}
```

**Response 201 (infeasible)**:
```json
{
  "data": {
    "recourse_id": "uuid",
    "status": "infeasible",
    "reason": "no_evidence",
    "detail": "No usable CandidateFacts found for this resume.",
    "partial_result": {
      "edits": [],
      "total_edit_cost": 0.0,
      "projected_score": 0.42
    },
    "constraints_violated": ["threshold"]
  }
}
```

**Errors**: 404, 422

---

#### 10. `POST /api/recourse/{id}/verify`

**Request**: Empty body (recourse_id from path)

**Response 200**:
```json
{
  "data": {
    "recourse_id": "uuid",
    "verification_reports": [
      {
        "edit_id": "uuid",
        "methods_used": ["source_span_match", "entailment", "entity_check"],
        "evidence_fact_ids": ["uuid"],
        "assigned_status": "Supported",
        "entailment_score": 0.82,
        "rationale": "Proposed text is fully entailed by CandidateFact cf-123 with no new entities."
      }
    ]
  }
}
```

**Errors**: 404

---

#### 11. `POST /api/recourse/{id}/accept`

**Request**:
```json
{
  "accepted_edit_ids": ["uuid", "uuid"],
  "baseline_method": "proposed",
  "random_seed": 42
}
```

**Response 201**:
```json
{
  "data": {
    "resume_version_id": "uuid",
    "version_number": 2,
    "ats_score": 0.54,
    "decision": "pass",
    "experiment_run_id": "uuid",
    "download_urls": {
      "txt": "/api/resumes/versions/uuid/download?format=txt",
      "pdf": "/api/resumes/versions/uuid/download?format=pdf"
    }
  }
}
```

**Errors**: 404, 422

---

#### 12. `POST /api/experiments`

**Request**:
```json
{
  "resume_id": "uuid",
  "job_description_id": "uuid",
  "model_configuration": { /* see schema above */ },
  "baseline_method": "proposed",
  "original_score": 0.42,
  "final_score": 0.54,
  "threshold": 0.5,
  "decision_flipped": true,
  "total_edit_cost": 0.18,
  "grounding_metrics": { /* see schema above */ },
  "random_seed": 42
}
```

**Response 201**:
```json
{
  "data": { /* full ExperimentRun record */ }
}
```

**Errors**: 404 (invalid resume_id/jd_id), 422 (invalid baseline_method)

---

#### 13. `GET /api/experiments`

**Query Parameters**: `baseline_method`, `start_date` (ISO 8601), `end_date` (ISO 8601),
`threshold`, `model_name`, `page` (default 1), `page_size` (default 20)

**Response 200**:
```json
{
  "data": {
    "items": [
      {
        "id": "uuid",
        "baseline_method": "proposed",
        "original_score": 0.42,
        "final_score": 0.54,
        "decision_flipped": true,
        "created_at": "2024-01-15T10:00:00Z"
      }
    ],
    "total": 47,
    "page": 1,
    "page_size": 20
  }
}
```

---

#### 14. `GET /api/experiments/{id}`

**Response 200**:
```json
{
  "data": { /* full ExperimentRun record */ }
}
```

**Errors**: 404

---

#### 15. `GET /api/experiments/{id}/report`

**Response 200**:
```json
{
  "data": {
    "run_id": "uuid",
    "summary": {
      "baseline_method": "proposed",
      "original_score": 0.42,
      "final_score": 0.54,
      "decision_flipped": true,
      "total_edit_cost": 0.18,
      "grounding_metrics": { /* ... */ }
    },
    "model_configuration": { /* ... */ },
    "all_edits": [ /* all ProposedEdits including rejected */ ],
    "accepted_edits": [ /* accepted only */ ],
    "verification_reports": [ /* per-edit */ ]
  }
}
```

**Errors**: 404

---

## Counterfactual Optimization Formulation

### Edit Cost Formula

For each `ProposedEdit` *e*, the edit cost *C(e)* is:

```
C(e) = 0.25 × norm_levenshtein(e.original_text, e.proposed_text)
     + 0.25 × (Δstatements / total_statements_in_resume)
     + 0.25 × (1 − SBERT_cosine(e.original_text, e.proposed_text))
     + 0.25 × (moved_sections / total_sections_in_resume)
```

Where:
- **norm_levenshtein**: Levenshtein distance divided by `max(len(original), len(proposed))`
  → range [0, 1]
- **Δstatements**: count of sentences/bullets changed by this edit
- **total_statements**: total sentence/bullet count in the resume
- **1 − SBERT_cosine**: semantic change; 0 = identical meaning, 1 = completely different
- **moved_sections**: sections displaced by this edit (0 for non-reorder edits)
- **total_sections**: count of named sections (e.g., Experience, Skills, Education)

The four component weights are configurable per `ExperimentRun` via `OptimizationConfig`.
Default is equal weighting at 0.25 each.

Total cost for a subset S: **C(S) = Σ C(e) for e in S**

### Search Algorithm

The optimizer performs a **bounded subset enumeration** with cost-guided pruning:

```
Algorithm: BoundedSubsetSearch(edits E, config):
  1. Sort E ascending by edit_cost (greedy warm start)
  2. Initialize best_feasible = None, best_cost = ∞
  3. For each subset S of E (enumerate in size order, smallest first):
     a. Apply S to base resume → candidate_text
     b. score = ATS_Scorer.score(candidate_text, jd_text, config)
     c. If score < threshold: skip (constraint a violated)
     d. verify_structure(candidate_text, base_resume) → check constraints b, c
     e. If any structural constraint violated: skip
     f. check_fabrication(candidate_text, evidence_bank) → constraint d
     g. If fabrication detected: skip
     h. cost = C(S)
     i. If cost < best_cost: update best_feasible = S, best_cost = cost
  4. If best_feasible is None:
     Return infeasible + partial_result (lowest-cost S found, even if failing threshold)
  5. Verify minimality: for each e in best_feasible:
     S' = best_feasible \ {e}
     If ATS_Scorer.score(apply(S', resume)) >= threshold AND all constraints hold:
       best_feasible = S' (remove redundant edit)
  6. Return feasible result with best_feasible
```

**Complexity bound**: With max 20 edits per generation (Req 5.7), the worst-case search
space is 2^20 ≈ 1M subsets. Cost-based pruning (branch-and-bound) typically reduces
effective search to well under 10K evaluations. ATS scoring during search uses cached
embeddings; the incremental cost of applying edits is O(n × len(resume)).

### Infeasibility

When no feasible subset exists:
- `status = "infeasible"`
- `constraints_violated`: list from `{"threshold", "support", "fabrication", "fact_preservation"}`
- `partial_result`: the lowest-cost subset found during search (may be empty if all edits
  violate fabrication), with its `total_edit_cost` and `projected_score`

The fabrication constraint is **never relaxed**. If introducing any ungrounded entity is
the only path to threshold crossing, the system returns infeasible.

---

## Evidence Verification Protocol

### Decision Rules (Applied in Order)

The Verifier applies these four rules in strict order; the first matching rule determines
the status:

| Rule | Condition | Assigned Status |
|---|---|---|
| (d) | New entity or skill detected that is absent from ALL referenced CandidateFacts | **Unsupported** |
| (a) | Source-span match found AND entailment ≥ 0.5 AND no new entity/skill | **Supported** |
| (b) | Source-span match found AND (entailment < 0.5 OR minor related entity) | **Partially Supported** |
| (c) | No source-span match AND entailment ≥ 0.5 AND no new entity/skill | **Needs Confirmation** |

Rule (d) is checked first because fabrication must be caught regardless of other signals.

### Verification Steps

```
For each ProposedEdit e:
  1. source_span_match = check_span_overlap(e.proposed_text, fact.source_span)
  2. entities_in_proposed = spaCy_NER(e.proposed_text)
  3. entities_in_evidence = union(spaCy_NER(f.claim_text) for f in e.referenced_facts)
  4. new_entities = entities_in_proposed - entities_in_evidence
  5. entailment_score = cross_encoder.predict(premise=fact.claim_text, hypothesis=e.proposed_text)
  6. Apply decision rules (d) → (a) → (b) → (c)
  7. If LLM advisory enabled AND status == Unsupported:
       llm_result = llm.check(e.proposed_text, fact.claim_text)
       If llm_result.confidence > 0.7: status = Needs Confirmation  # only upgrade, never to Supported
  8. Record VerificationReport
```

### LLM Advisory Constraints

- LLM advisory is **optional** and gated by `LLMConfig.enabled`
- LLM output may **only** upgrade `Unsupported → Needs Confirmation`
- LLM cannot set `Supported` or `Partially Supported` unilaterally
- `methods_used` in the report includes `"llm_advisory"` when LLM was consulted

---

## Frontend Architecture

### Route Table

| Route | Screen | Session Guard |
|---|---|---|
| `/` | Dashboard | None |
| `/input` | Resume & JD Input | None |
| `/evidence` | Candidate Evidence Review | Yes → redirect `/input` |
| `/analysis` | ATS Analysis | Yes → redirect `/input` |
| `/recommendations` | Counterfactual Recommendations | Yes → redirect `/input` |
| `/comparison` | Final Resume Comparison | Yes → redirect `/input` |
| `/research` | Research Evaluation Dashboard | None |

### Session Guard

A `SessionGuard` higher-order component wraps the four protected routes. It reads
`activeSession` from a React context (backed by `localStorage`). If `activeSession` is
null or missing `resumeId` / `jobDescriptionId`, it redirects to `/input` with
`?redirect=<original_path>` and displays: *"Please upload a resume and job description first."*

### TanStack Query Usage

```typescript
// Key factory
const queryKeys = {
  resume: (id: string) => ['resumes', id] as const,
  evidence: (candidateId: string) => ['candidates', candidateId, 'evidence'] as const,
  analysis: (resumeVersionId: string) => ['analysis', resumeVersionId] as const,
  recourse: (recourseId: string) => ['recourse', recourseId] as const,
  experiments: (filters: ExperimentFilters) => ['experiments', filters] as const,
};
```

- All GET requests use `useQuery` with stale-time 60s
- All POST/PATCH mutations use `useMutation` with optimistic invalidation
- Loading state: `QueryStatus === 'pending'` → `<LoadingSpinner />`
- Error state: `QueryStatus === 'error'` → `<ErrorBanner message={error.message} onRetry={refetch} />`

### Diff View (Final Resume Comparison)

The sentence-level diff on `/comparison` is computed client-side using the
`diff-match-patch` library:

```typescript
const diffs = computeSentenceDiff(baselineContent, revisedContent);
// additions: green highlight
// deletions: red strikethrough
// unchanged: plain text
```

Granularity: sentences are split on `/(?<=[.!?])\s+/` before diffing.

### Research Dashboard Charts

`MethodComparisonChart` renders a Recharts `<BarChart>` with three bar groups
(original_resume, generic_llm, proposed) across five metrics:

```typescript
const metrics = [
  { key: 'flip_rate', label: 'Flip Rate' },
  { key: 'mean_edit_cost', label: 'Mean Edit Cost' },
  { key: 'mean_grounding_rate', label: 'Mean Grounding Rate' },
  { key: 'mean_unsupported_rate', label: 'Mean Unsupported Rate' },
  { key: 'mean_fact_preservation', label: 'Mean Fact Preservation' },
];
```

---

## Research Pipeline (CLI Entry Point)

A standalone CLI (`research_cli.py`) runs experiments independently of the web UI.
It reads experiment configs from YAML files and is fully reproducible.

### CLI Interface

```bash
python research_cli.py run \
  --config experiments/config_001.yaml \
  --resume resumes/candidate_a.pdf \
  --jd job_descriptions/jd_001.txt \
  --baseline proposed \
  --seed 42

python research_cli.py compare \
  --run-ids uuid1 uuid2 uuid3 \
  --output results/comparison_report.json
```

### Experiment Config YAML Structure

```yaml
experiment_id: exp_001
baseline_method: proposed   # original_resume | generic_llm | proposed
random_seed: 42
model_configuration:
  sbert_model: all-MiniLM-L6-v2
  spacy_model: en_core_web_trf
  ats_skill_weight: 0.5
  ats_sbert_weight: 0.5
  threshold: 0.5
  edit_cost_weights:
    levenshtein: 0.25
    changed_statements: 0.25
    semantic_change: 0.25
    moved_sections: 0.25
```

The CLI records results via `Experiment_Logger.create_run()` — identical to the web
path — ensuring all runs appear in the Research Dashboard.

---

## Security and Privacy

### No Credentials in Source

All secrets and external configuration are loaded from environment variables.
A `.env.example` file documents all required variables with placeholder values:

```
DATABASE_URL=postgresql://user:password@localhost:5432/recourse_db
UPLOAD_DIR=/tmp/uploads
MAX_FILE_SIZE_MB=10
MAX_MANUAL_CHARS=50000
# Optional S3-compatible storage
S3_ENDPOINT_URL=
S3_BUCKET_NAME=
S3_ACCESS_KEY=
S3_SECRET_KEY=
# Optional LLM advisory
LLM_API_KEY=
LLM_MODEL=
```

### Upload Limits

- File upload: configurable via `MAX_FILE_SIZE_MB` env var (default 10 MB)
- Manual text: configurable via `MAX_MANUAL_CHARS` env var (default 50,000)
- FastAPI middleware enforces the file size limit before the request reaches the handler

### File Storage Abstraction

```python
class StorageBackend(Protocol):
    def save(self, file_id: str, data: bytes) -> str: ...   # returns path/URL
    def load(self, path: str) -> bytes: ...
    def delete(self, path: str) -> None: ...
```

`LocalFileStorage` is the default. `S3CompatibleStorage` activates when `S3_ENDPOINT_URL`
is set. This keeps local development simple while allowing cloud deployment without
code changes.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Source Span Validity

*For any* document ingested by the Ingestion_Service, every extracted segment's source
span must satisfy `0 ≤ span.start < span.end ≤ len(extracted_text)`.

**Validates: Requirements 1.2, 2.4, 3.2**

---

### Property 2: Extraction Error Envelope Consistency

*For any* failure mode in Ingestion_Service (file size exceeded, unsupported format,
empty extraction, library exception), the HTTP error response must contain a top-level
`error` field with both a machine-readable `code` string and a human-readable `message`
string, and must NOT create a partial ResumeDocument record.

**Validates: Requirements 1.6, 1.7, 1.8, 1.9**

---

### Property 3: Manual Ingestion Round Trip

*For any* non-empty string of up to 50,000 characters submitted to
`POST /api/resumes/manual`, a subsequent `GET /api/resumes/{id}` must return the same
text in `extracted_text` and `document_type` must equal `"manual"`.

**Validates: Requirements 1.10, 1.12**

---

### Property 4: JobRequirement Importance Invariant

*For any* `JobRequirement` record, the `importance` field must be exactly one of
`"required"` or `"preferred"`. For any requirement extracted from text containing no
signal words, `importance` must equal `"required"`.

**Validates: Requirements 2.3**

---

### Property 5: Skill Normalization Completeness

*For any* skill name appearing in a `JobRequirement`, the `normalized_skills` array must
be non-empty and contain at least one non-empty string (either a canonical form or the
original skill name unchanged).

**Validates: Requirements 2.6**

---

### Property 6: CandidateFact Field Completeness

*For any* auto-extracted `CandidateFact`, all nine required fields must be present and
non-null: `id`, `candidate_id`, `claim_text`, `claim_type`, `source_document_id`,
`source_span`, `verification_status`, `original_claim_text`, `metadata`. The
`verification_status` must equal `"Needs Confirmation"` at creation time.

**Validates: Requirements 3.2, 3.3**

---

### Property 7: original_claim_text Immutability

*For any* sequence of PATCH operations applied to a `CandidateFact`, the
`original_claim_text` field must remain byte-for-byte identical to the value set at
creation time.

**Validates: Requirements 3.9**

---

### Property 8: ATS Score Range and Decision Consistency

*For any* valid resume text, job description text, weight configuration, and threshold,
the `ATS_Scorer` must produce a `total_score` in `[0.0, 1.0]`, and the `decision` must
equal `"pass"` if and only if `total_score >= threshold`.

**Validates: Requirements 4.1, 4.3**

---

### Property 9: ATS Scorer Determinism

*For any* fixed (resume_text, jd_text, model_version, skill_overlap_weight,
sbert_weight, threshold) tuple, calling `ATS_Scorer.score()` twice must produce
identical `total_score`, `skill_overlap_score`, `semantic_similarity_score`, and
`decision` values.

**Validates: Requirements 4.5**

---

### Property 10: ResumeVersion Monotonic Numbering

*For any* `original_resume_id`, the sequence of `version_number` values across all
associated `ResumeVersion` records must form a gapless, strictly increasing sequence
starting at 1. Each new version must have `version_number = max_existing + 1`.

**Validates: Requirements 4.6, 9.1**

---

### Property 11: ProposedEdit Type and Grounding Invariants

*For any* `ProposedEdit` generated by the `Recourse_Engine`:
- `edit_type` must be in `{rephrase, surface_qualification, reorder, normalize_terminology, reorganize_sections, remove_redundancy}`
- all referenced `CandidateFact` records must have `verification_status ≠ "Unsupported"`
- `len(job_requirement_ids) ≥ 1`
- `len(evidence_fact_ids) ≥ 1`

**Validates: Requirements 5.1, 5.2, 5.6**

---

### Property 12: No Fabrication in Proposed Edits

*For any* `ProposedEdit`, every named entity and skill extracted from `proposed_text` must
also appear in at least one of the `CandidateFact` records linked via `evidence_fact_ids`.
No entity introduced in `proposed_text` may be absent from the Evidence Bank.

**Validates: Requirements 5.3, 6.7**

---

### Property 13: Rephrase Semantic Preservation

*For any* `ProposedEdit` with `edit_type = "rephrase"`, the Sentence-BERT cosine
similarity between `original_text` and `proposed_text` must be ≥ 0.85.

**Validates: Requirements 5.4**

---

### Property 14: Edit Cost Formula Correctness

*For any* `ProposedEdit` with known component values, the stored `edit_cost` must equal:

```
0.25 × norm_levenshtein + 0.25 × changed_statements_ratio +
0.25 × (1 − sbert_cosine) + 0.25 × moved_sections_ratio
```

within a floating-point tolerance of 1e-9.

**Validates: Requirements 6.2**

---

### Property 15: Optimizer Structural Invariants on Revised Resume

*For any* feasible optimization result, the revised resume produced by applying the
accepted edit set must: (a) contain all named sections present in the original resume,
(b) have an unchanged contact block (name, email, phone), and (c) contain text traceable
to every `CandidateFact` in the Evidence Bank.

**Validates: Requirements 6.3**

---

### Property 16: Entailment Score Bounds

*For any* `VerificationReport`, the `entailment_score` must be in `[0.0, 1.0]`.

**Validates: Requirements 7.2**

---

### Property 17: Verification Status Decision Rule Correctness

*For any* `ProposedEdit` submitted for verification, the assigned `verification_status`
must follow the four decision rules in strict order: (d) new entity → Unsupported takes
priority; then (a) span match + entailment ≥ 0.5 + no new entity → Supported; then
(b) span match + (entailment < 0.5 or minor entity) → Partially Supported; then
(c) no span match + entailment ≥ 0.5 + no new entity → Needs Confirmation.

**Validates: Requirements 7.4**

---

### Property 18: LLM Advisory Cannot Produce Supported Status

*For any* verification run where the LLM advisory is the only positive signal (no
source-span match, no satisfying entailment from the base model), the resulting
`verification_status` must not be `"Supported"` or `"Partially Supported"`. The LLM
may only elevate from `"Unsupported"` to `"Needs Confirmation"`.

**Validates: Requirements 7.3**

---

### Property 19: Verification Completeness

*For any* batch of N `ProposedEdit` records submitted to the Verifier, exactly N
`VerificationReport` records must be returned — no edit may be left without a status.

**Validates: Requirements 7.8**

---

### Property 20: Explanation Card Completeness

*For any* accepted `ProposedEdit`, its explanation card must contain all seven required
fields: prose description, reason for ATS improvement, evidence fact IDs and claim texts,
job requirement IDs and requirement texts, `score_contribution`, `edit_cost`, and
`verification_status`.

**Validates: Requirements 8.1, 8.2**

---

### Property 21: Candidate Confirm/Reject Status Transitions

*For any* `ProposedEdit` with `verification_status = "Needs Confirmation"`:
- After a Confirm action: `verification_status` must equal `"Supported"`
- After a Reject action: `verification_status` must equal `"Unsupported"`

**Validates: Requirements 8.5, 8.6**

---

### Property 22: Original Resume Immutability

*For any* recourse acceptance operation, the `ResumeDocument` record and the
`ResumeVersion` with `version_number = 1` must remain byte-for-byte identical to their
state before the operation. Acceptance must never modify existing records.

**Validates: Requirements 9.2**

---

### Property 23: ExperimentRun Field Completeness and Rate Bounds

*For any* created `ExperimentRun`, all 13 required fields must be present. The three
values inside `grounding_metrics` (`evidence_grounding_rate`, `unsupported_claim_rate`,
`original_fact_preservation_rate`) must each be in `[0.0, 1.0]`.

**Validates: Requirements 10.1, 10.5**

---

### Property 24: ExperimentRun Append-Only Immutability

*For any* existing `ExperimentRun` record, no update operation (via the API or internal
service calls) must alter any of its fields after creation.

**Validates: Requirements 10.8**

---

### Property 25: API Response Envelope Consistency

*For any* API request:
- A successful response must contain a top-level `data` field and must NOT contain a
  top-level `error` field.
- An error response must contain a top-level `error` field with `code` and `message`
  sub-fields, and must NOT contain a top-level `data` field.

**Validates: Requirements 13.2, 13.3, 13.4, 13.5**

---

### Property 26: Experiment List Filter AND Semantics

*For any* combination of active filters on `GET /api/experiments`, every returned
`ExperimentRun` summary must satisfy ALL active filter conditions simultaneously.

**Validates: Requirements 11.2**

---

### Property 27: GET /api/experiments Summary Field Completeness

*For any* page of results returned by `GET /api/experiments`, every item must contain
exactly the six summary fields: `id`, `baseline_method`, `original_score`, `final_score`,
`decision_flipped`, `created_at`.

**Validates: Requirements 11.6**

---

## Error Handling

### Error Code Registry

| Code | HTTP Status | Meaning |
|---|---|---|
| `FILE_TOO_LARGE` | 413 | Upload exceeds `MAX_FILE_SIZE_MB` |
| `UNSUPPORTED_FILE_TYPE` | 415 | Not PDF or DOCX |
| `EMPTY_EXTRACTION` | 422 | Extraction produced zero non-whitespace chars |
| `EXTRACTION_FAILED` | 422 | Library exception during extraction |
| `INVALID_REQUEST` | 422 | Pydantic schema validation failure |
| `TEXT_TOO_LONG` | 422 | Manual text or JD exceeds character limit |
| `TEXT_EMPTY` | 422 | Empty body for text-only endpoints |
| `NOT_FOUND` | 404 | Requested resource does not exist |
| `CONFLICT` | 409 | Uniqueness constraint violation |
| `SBERT_UNAVAILABLE` | 502 | Sentence-BERT model failed to produce embedding |
| `INFEASIBLE_NO_EVIDENCE` | 200 | No usable CandidateFacts found |
| `INFEASIBLE_ALL_UNSUPPORTED` | 200 | All facts are marked Unsupported |
| `INFEASIBLE_NO_REQUIREMENT_MATCH` | 200 | No facts match any JobRequirement |
| `EXPORT_FAILED` | 500 | File serialization error during export |
| `INVALID_BASELINE_METHOD` | 422 | baseline_method not in allowed set |
| `IMMUTABLE_RECORD` | 409 | Attempt to modify an append-only ExperimentRun |

### FastAPI Exception Handlers

Global exception handlers in `app/main.py` catch:
- `RequestValidationError` → 422 with `INVALID_REQUEST` code
- `ResourceNotFoundError` → 404
- `ImmutableRecordError` → 409 with `IMMUTABLE_RECORD` code
- Unhandled `Exception` → 500 with `INTERNAL_ERROR` code (no stack trace in response)

---

## Testing Strategy

### Backend (pytest)

**Unit Tests — per service module** (`tests/unit/<module>/`):

- `test_ingestion_service.py` — extraction round-trip, error envelopes, OCR fallback
- `test_jd_analyzer.py` — importance assignment, normalization, source span bounds
- `test_evidence_bank.py` — original_claim_text immutability, PATCH validation
- `test_ats_scorer.py` — score range, determinism, weight configuration, decision rule
- `test_recourse_engine.py` — edit type enumeration, fabrication guard, rephrase similarity
- `test_optimizer.py` — edit cost formula, minimality, infeasibility handling
- `test_verifier.py` — all 4 decision rule branches, LLM advisory limits, report completeness
- `test_experiment_logger.py` — append-only enforcement, field completeness, grounding rate bounds

**Integration Tests** (`tests/integration/`):

- `test_api_resumes.py` — FastAPI test client, full upload/manual round trips
- `test_api_analysis.py` — scoring request lifecycle, ResumeVersion creation
- `test_api_recourse.py` — generate → verify → accept lifecycle including infeasible paths
- `test_api_experiments.py` — ExperimentRun CRUD, paginated list, filter AND semantics
- `test_db_constraints.py` — FK enforcement, enum constraint, cascade delete

**Key Test Cases** (explicitly required by specification):

1. **Unsupported claim rejection**: A `CandidateFact` with `verification_status = "Unsupported"` must never appear as the sole grounding fact for any `ProposedEdit`.
2. **Infeasible optimization explicit failure**: When no feasible edit subset exists, the response must have `status = "infeasible"`, a non-empty `constraints_violated` list, and a `partial_result` field.
3. **Edit cost calculation**: For a `ProposedEdit` with known levenshtein/statements/sbert/sections values, the stored `edit_cost` must match the formula result within 1e-9.
4. **Rephrase similarity enforcement**: A `rephrase` edit generated with SBERT similarity < 0.85 between original and proposed text must be rejected at generation time.
5. **Deterministic scoring**: Two calls to `ATS_Scorer.score()` with identical inputs must return identical results.
6. **Append-only experiment records**: After `ExperimentRun` creation, any attempt to modify the record (via service layer) must raise `ImmutableRecordError`.

**Property-Based Tests** (`tests/property/`):

Using `hypothesis` (Python):

```python
# Example: Property 9 — ATS Scorer Determinism
@given(
    resume_text=text(min_size=1, max_size=5000),
    jd_text=text(min_size=1, max_size=5000),
    weight=floats(min_value=0.0, max_value=1.0),
    threshold=floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=100)
def test_ats_scorer_determinism(resume_text, jd_text, weight, threshold):
    """Feature: verifiable-counterfactual-recourse, Property 9: ATS scorer determinism"""
    config = ScoringConfig(skill_overlap_weight=weight, sbert_weight=1.0-weight, threshold=threshold)
    result1 = scorer.score(resume_text, jd_text, config)
    result2 = scorer.score(resume_text, jd_text, config)
    assert result1.total_score == result2.total_score
    assert result1.decision == result2.decision
```

Each property-based test is tagged with a comment matching:
`Feature: verifiable-counterfactual-recourse, Property {N}: {property_text}`

Minimum 100 iterations per property test (Hypothesis default `max_examples=100`).

### Frontend (Vitest + React Testing Library)

- Component unit tests for each screen, explanation card, diff view
- TanStack Query mock handlers via `msw` (Mock Service Worker)
- Route guard tests: navigating to `/evidence` without session → verify redirect to `/input`
- Research Dashboard: chart data grouping, filter form interactions

### CI Pipeline

```yaml
jobs:
  backend:
    - ruff lint + mypy type check
    - pytest tests/ --cov=app --cov-report=xml
  frontend:
    - eslint + tsc --noEmit
    - vitest run --coverage
```

---

## Integration Milestones

| Milestone | Owner(s) | Deliverables |
|---|---|---|
| 1 | Varun, Vipul | Alembic schema, all 6 ORM models, Ingestion_Service, Evidence_Extractor |
| 2 | Vaishnavi, Dhruv | ATS_Scorer, Evidence_Bank (CRUD), JD_Analyzer |
| 3 | Varun | Recourse_Engine, Optimizer, infeasibility reporting |
| 4 | Vaishnavi | Verifier (all 4 decision rules), Explanation_Service |
| 5 | Yash, Shahin | All 7 frontend screens, Export_Service, Research_Dashboard |
| 6 | All / Varun integrates | Experiment_Logger, end-to-end tests, evaluation run |

All feature branches target `integration`. Only Varun merges into `integration` and `main`.

Branch naming:
- `varun/<task-slug>`, `vaishnavi/<task-slug>`, `vipul/<task-slug>`
- `dhruv/<task-slug>`, `yash/<task-slug>`, `shahin/<task-slug>`
