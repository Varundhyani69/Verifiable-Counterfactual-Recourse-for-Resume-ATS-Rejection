# Contributing Guide

> **Only Varun merges into `integration` and `main`.**
> Every other team member opens PRs targeting `integration`.

---

## Branch Naming Convention

Create your branch from `integration` using the pattern `<your-name>/<task-slug>`:

| Team member | Example branches |
|---|---|
| **Varun** | `varun/db-schema` · `varun/recourse-engine` · `varun/optimizer` |
| **Vaishnavi** | `vaishnavi/ats-scorer` · `vaishnavi/verifier` · `vaishnavi/explanation-service` |
| **Vipul** | `vipul/ingestion-service` · `vipul/evidence-extractor` · `vipul/experiment-logger` |
| **Dhruv** | `dhruv/jd-analyzer` · `dhruv/evidence-bank` |
| **Yash** | `yash/frontend-setup` · `yash/frontend-screens-1` · `yash/api-integration-tests` |
| **Shahin** | `shahin/export-service` · `shahin/research-dashboard` · `shahin/e2e-tests` |

---

## Starting a Task

```bash
# 1. Make sure your local integration branch is up to date
git checkout integration
git pull origin integration

# 2. Create your feature branch
git checkout -b <your-name>/<task-slug>

# 3. Build and test locally
# backend
pytest tests/ -q
# frontend (inside /frontend)
npm run test

# 4. Rebase before opening a PR
git fetch origin
git rebase origin/integration

# 5. Push
git push -u origin <your-name>/<task-slug>
```

---

## Pull Request Template

When you open a PR targeting `integration`, your description **must** include all four sections:

```
## Summary
<!-- What changed and why -->

## Task ID
<!-- Link to the task in .kiro/specs/verifiable-counterfactual-recourse/tasks.md -->
<!-- e.g. Task 5 — Resume ingestion service -->

## Tests run
<!-- Paste the test output or a summary -->
<!-- e.g. pytest tests/unit/test_ingestion_service.py — 12 passed, 0 failed -->

## Downstream dependencies
<!-- List any other modules/PRs that depend on this being merged first -->
<!-- e.g. Evidence extractor (Task 6) depends on this -->
```

---

## Merge Rules

1. All PRs target `integration` — **never open a PR directly to `main`**.
2. At least **one teammate** (other than the author) must approve the PR.
3. **Varun performs the final review and merge** into `integration`.
4. Only Varun merges `integration` → `main` at the end of the project.

No one other than Varun should click the merge button on `integration` or `main`.

---

## Definition of Done

A task is done when **all five** of the following are true:

- [ ] All acceptance criteria for the task are implemented and verified
- [ ] All unit tests for the task pass locally (`pytest` / `vitest`)
- [ ] Branch is rebased on latest `integration` with no conflicts
- [ ] PR description is complete (all four sections above are filled in)
- [ ] CI checks pass on the PR (ruff + mypy + pytest / eslint + tsc + vitest)

---

## Integration Milestones

Milestones are gates — Varun reviews and merges each milestone before the next begins.

```
Milestone 1  (Varun)
  └─ DB schema + ORM + storage backend + project skeleton
       │
       ├── Milestone 2  (Vipul, Dhruv, Vaishnavi — parallel)
       │     ├─ Vipul:      Resume ingestion + Evidence extractor
       │     ├─ Dhruv:      JD analyzer + Evidence bank
       │     └─ Vaishnavi:  ATS scorer
       │
       └── Milestone 3  (Varun + Vaishnavi — parallel)
             ├─ Varun:      Recourse engine + Optimizer
             └─ Vaishnavi:  Verifier + Explanation service
                   │
                   └── Milestone 4  (Yash + Shahin — parallel)
                         ├─ Yash:    Frontend setup + 4 screens + API tests
                         └─ Shahin:  Export service + Comparison screen + Dashboard + E2E
                               │
                               └── Milestone 5  (Vipul + Varun — parallel)
                                     ├─ Vipul:  Experiment logger
                                     └─ Varun:  Research CLI + Final integration
```

### Module dependency order (for reference)

1. Database schema and shared models
2. Resume ingestion + evidence extraction
3. JD analysis + ATS scoring
4. Recourse generation + optimization
5. Evidence verification + recourse explanation
6. Resume export + experiment logging
7. Frontend screens + research evaluation dashboard

---

## Environment Setup

```bash
# Clone and install backend deps
git clone <repo-url>
cd "Verifiable Counterfactual Recourse for Resume–ATS Rejection"
pip install -e ".[dev]"

# Copy env vars and fill in values
cp .env.example .env

# Download NLP models
python -m spacy download en_core_web_sm
# (SBERT model downloads automatically on first use)

# Run database migrations
alembic upgrade head

# Install frontend deps
cd frontend
npm install
cd ..

# Run the backend
uvicorn backend.app.main:app --reload

# Run all tests
pytest tests/ -q           # backend
cd frontend && npm test    # frontend
```

---

## Secrets Policy

- **Never commit `.env` or any file containing real credentials.**
- `.env.example` contains only placeholder values — this is safe to commit.
- All secret values are loaded from environment variables at runtime.
- If you accidentally commit a secret, notify Varun immediately to rotate it.
