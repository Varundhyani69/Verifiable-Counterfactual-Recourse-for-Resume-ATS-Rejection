# Verifiable Counterfactual Recourse for Resume–ATS Rejection

> A research-oriented full-stack application that identifies the **smallest truthful,
> evidence-supported changes** a candidate can make to their resume to cross a simulated
> ATS screening threshold — without inventing skills or qualifications.

---

## Research Question

> Can truth-constrained, minimal-edit counterfactual resume recommendations achieve a
> comparable screening decision flip rate to generic LLM-generated recommendations while
> producing **fewer unsupported claims** and requiring **smaller edits**?

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, TypeScript, TanStack Query, Recharts |
| Backend | Python 3.11, FastAPI, Pydantic v2 |
| Database | PostgreSQL 15, SQLAlchemy 2, Alembic |
| NLP | Sentence-Transformers (SBERT), spaCy, cross-encoder NLI |
| Document parsing | PyMuPDF, python-docx, pytesseract |
| Export | reportlab |

---

## Quick Start

```bash
# 1. Install Python deps
pip install -e ".[dev]"

# 2. Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL, UPLOAD_DIR, etc.

# 3. Download NLP models
python -m spacy download en_core_web_sm

# 4. Run database migrations
alembic upgrade head

# 5. Start the API
uvicorn backend.app.main:app --reload

# 6. Install and start the frontend
cd frontend
npm install
npm run dev
```

API docs available at `http://localhost:8000/docs` once the server is running.

---

## Module Dependency Graph

```
shared models (SQLAlchemy ORM, Pydantic schemas, enums)
        │
        ├─► Ingestion_Service ──► Evidence_Extractor ──► Evidence_Bank
        │
        ├─► JD_Analyzer
        │
        ├─► ATS_Scorer (needs: Ingestion, JD_Analyzer, Evidence_Bank)
        │
        ├─► Recourse_Engine (needs: ATS_Scorer, Evidence_Bank)
        │         │
        │         └─► Optimizer (needs: ATS_Scorer, Recourse_Engine)
        │
        ├─► Verifier (needs: Evidence_Bank, Recourse_Engine)
        │
        ├─► Explanation_Service (needs: Verifier, Recourse_Engine)
        │
        ├─► Export_Service (needs: Explanation_Service)
        │
        └─► Experiment_Logger (needs: all above)
```

---

## Team & Ownership

| Person | Solo responsibility |
|---|---|
| **Varun** | Project skeleton · DB schema + ORM · storage · recourse engine · optimizer · research CLI · **final integration** |
| **Vaishnavi** | ATS scorer · evidence verifier · explanation service |
| **Vipul** | Resume ingestion · evidence extractor · experiment logger |
| **Dhruv** | JD analyzer · evidence bank |
| **Yash** | Frontend setup + routing · 4 frontend screens · API integration tests |
| **Shahin** | Export service · final comparison screen · research dashboard · E2E tests |

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch naming convention, PR template,
merge rules, and Definition of Done.

---

## Project Spec

Full requirements, technical design, and task list live in:

```
.kiro/specs/verifiable-counterfactual-recourse/
  requirements.md   — 15 requirements, 100+ acceptance criteria
  design.md         — architecture, DB schema, API contracts, optimization formulation
  tasks.md          — solo ownership task breakdown, dependency graph, PR guide
```

---

## Running Tests

```bash
# Backend
pytest tests/ --cov=backend --cov-report=term-missing

# Frontend (inside /frontend)
npm run test

# Research CLI (after Milestone 5)
python research_cli.py run --config experiments/config_001.yaml \
  --resume <path> --jd <path> --baseline proposed --seed 42
```

---

## Disclaimer

This system uses a **simulated** ATS scoring model. Passing the simulated threshold does
**not** guarantee an interview or hiring decision with any employer. The model is a
research proxy, not a reproduction of any real employer's proprietary system.
