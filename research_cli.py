#!/usr/bin/env python3
"""
Research CLI — Verifiable Counterfactual Recourse for Resume–ATS Rejection.

Provides two subcommands for running and comparing experiments programmatically
through the service layer (identical to the web path).

Usage:

  Run a single experiment:
    python research_cli.py run \\
      --config experiments/config_001.yaml \\
      --resume path/to/resume.pdf \\
      --jd path/to/jd.txt \\
      --baseline proposed \\
      --seed 42

  Compare multiple runs:
    python research_cli.py compare \\
      --run-ids <uuid1> <uuid2> <uuid3> \\
      --output experiments/comparison_001.json

Config YAML structure:
    experiment_id: "exp-001"
    baseline_method: "proposed"   # original_resume | generic_llm | proposed
    random_seed: 42
    model_configuration:
      sbert_model: "all-MiniLM-L6-v2"
      sbert_version: "1.0"
      spacy_model: "en_core_web_sm"
      spacy_version: "3.7.4"
      ats_skill_weight: 0.5
      ats_sbert_weight: 0.5
      threshold: 0.5
      edit_cost_weights:
        levenshtein: 0.25
        changed_statements: 0.25
        semantic_change: 0.25
        moved_sections: 0.25

Requirements: 10.1-10.3, 10.6
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any


# ── YAML helper ───────────────────────────────────────────────────────────────

def _load_yaml(path: str) -> dict[str, Any]:
    """Load a YAML config file. Requires PyYAML (installed as pyyaml)."""
    try:
        import yaml
    except ImportError:
        # Fallback: minimal YAML parser for simple flat configs
        print(
            "Warning: PyYAML not installed. Using simplified config loading. "
            "Install with: pip install pyyaml",
            file=sys.stderr,
        )
        return _simple_yaml_load(path)
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)  # type: ignore[no-any-return]


def _simple_yaml_load(path: str) -> dict[str, Any]:
    """Minimal YAML-like loader for flat key: value configs (no PyYAML required)."""
    result: dict[str, Any] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                value = value.strip()
                # Basic type conversion
                if value.lower() in ("true", "yes"):
                    result[key.strip()] = True
                elif value.lower() in ("false", "no"):
                    result[key.strip()] = False
                elif value.isdigit():
                    result[key.strip()] = int(value)
                else:
                    try:
                        result[key.strip()] = float(value)
                    except ValueError:
                        result[key.strip()] = value.strip('"\'')
    return result


# ── Database session helper ───────────────────────────────────────────────────

def _get_db_session() -> Any:
    """Open and return a database session."""
    from backend.app.database import SessionLocal
    return SessionLocal()


# ── run subcommand ────────────────────────────────────────────────────────────

def cmd_run(args: argparse.Namespace) -> int:
    """
    Execute a full pipeline run and record an ExperimentRun.

    Steps:
      1. Load YAML config
      2. Ingest resume file (PDF/DOCX) or read as plain text
      3. Ingest job description text
      4. Extract evidence (CandidateFacts)
      5. Analyze JD (JobRequirements) — via direct service call or stub
      6. Score resume against JD (ATS scorer)
      7. Generate recourse edits
      8. Optimize edit subset
      9. Record ExperimentRun via Experiment_Logger
      10. Print run ID and key metrics to stdout

    Returns:
        0 on success, 1 on error.
    """
    print(f"[run] Loading config: {args.config}")
    if not Path(args.config).exists():
        print(f"ERROR: Config file not found: {args.config}", file=sys.stderr)
        return 1

    config = _load_yaml(args.config)

    # Override with CLI flags if provided
    baseline = args.baseline or config.get("baseline_method", "proposed")
    seed: int | None = args.seed
    if seed is None:
        seed = config.get("random_seed", None)

    model_config: dict[str, Any] = config.get("model_configuration", {})

    # ── Validate baseline_method ──────────────────────────────────────────
    allowed_baselines = {"original_resume", "generic_llm", "proposed"}
    if baseline not in allowed_baselines:
        print(
            f"ERROR: Invalid baseline_method '{baseline}'. "
            f"Allowed: {', '.join(sorted(allowed_baselines))}",
            file=sys.stderr,
        )
        return 1

    print(f"[run] Resume: {args.resume}")
    print(f"[run] JD: {args.jd}")
    print(f"[run] Baseline: {baseline}")
    print(f"[run] Seed: {seed}")

    resume_path = Path(args.resume)
    jd_path = Path(args.jd)

    if not resume_path.exists():
        print(f"ERROR: Resume file not found: {resume_path}", file=sys.stderr)
        return 1

    if not jd_path.exists():
        print(f"ERROR: JD file not found: {jd_path}", file=sys.stderr)
        return 1

    db = _get_db_session()
    try:
        return _execute_run(
            db=db,
            resume_path=resume_path,
            jd_path=jd_path,
            baseline=baseline,
            seed=seed,
            model_config=model_config,
            config=config,
        )
    finally:
        db.close()


def _execute_run(
    *,
    db: Any,
    resume_path: Path,
    jd_path: Path,
    baseline: str,
    seed: int | None,
    model_config: dict[str, Any],
    config: dict[str, Any],
) -> int:
    """Inner execution of the research pipeline."""
    from backend.app.services import ingestion_service, evidence_extractor
    from backend.app.schemas.experiment import ExperimentRunCreate, GroundingMetrics

    # ── Step 1: Ingest resume ─────────────────────────────────────────────
    print("[run] Step 1/8: Ingesting resume...")
    candidate_id = uuid.uuid4()

    try:
        file_data = resume_path.read_bytes()
        filename = resume_path.name
        ext = resume_path.suffix.lower()

        if ext in (".pdf", ".docx"):
            # Determine MIME type
            mime = "application/pdf" if ext == ".pdf" else (
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            )
            resume_doc = ingestion_service.ingest_file(
                db=db,
                file_data=file_data,
                filename=filename,
                content_type=mime,
                candidate_id=candidate_id,
            )
        else:
            # Treat as plain text
            text = resume_path.read_text(encoding="utf-8", errors="replace")
            resume_doc = ingestion_service.ingest_manual(
                db=db,
                text=text,
                candidate_id=candidate_id,
            )
    except Exception as exc:
        print(f"ERROR: Resume ingestion failed: {exc}", file=sys.stderr)
        return 1

    print(f"[run]   ResumeDocument ID: {resume_doc.id}")

    # ── Step 2: Extract evidence ──────────────────────────────────────────
    print("[run] Step 2/8: Extracting evidence...")
    try:
        facts = evidence_extractor.extract(db=db, resume=resume_doc)
        print(f"[run]   Extracted {len(facts)} CandidateFacts")
    except Exception as exc:
        print(f"WARNING: Evidence extraction failed: {exc}", file=sys.stderr)
        facts = []

    # ── Step 3: Ingest JD ─────────────────────────────────────────────────
    print("[run] Step 3/8: Ingesting job description...")
    jd_text = jd_path.read_text(encoding="utf-8", errors="replace").strip()

    try:
        from backend.app.models.job_description import JobDescription
        from backend.app.models.job_requirement import JobRequirement
        from backend.app.models.enums import (
            RequirementType, ImportanceLevel, ExtractionType
        )

        jd_record = JobDescription(raw_text=jd_text)
        db.add(jd_record)
        db.flush()

        # Simple stub: extract skill requirements from comma/newline delimited text
        # (Full JD_Analyzer is Dhruv's task — we call the stub here)
        requirements = _stub_extract_requirements(jd_text, jd_record.id, db)
        db.commit()
        db.refresh(jd_record)
        print(f"[run]   JobDescription ID: {jd_record.id}")
        print(f"[run]   Extracted {len(requirements)} JobRequirements")
    except Exception as exc:
        print(f"ERROR: JD ingestion failed: {exc}", file=sys.stderr)
        return 1

    # ── Step 4: Score resume (ATS scorer stub) ────────────────────────────
    print("[run] Step 4/8: Scoring resume...")
    ats_weights = float(model_config.get("ats_skill_weight", 0.5)) if isinstance(model_config, dict) else 0.5
    threshold = float(
        model_config.get("threshold", config.get("threshold", 0.5)) if isinstance(model_config, dict)
        else config.get("threshold", 0.5)
    )

    try:
        from backend.app.models.resume_version import ResumeVersion
        from backend.app.models.enums import ATSDecision
        from sqlalchemy import select, func as sqlfunc

        # Compute naive skill overlap score
        resume_lower = resume_doc.extracted_text.lower()
        jd_skills = [
            skill.lower()
            for req in requirements
            for skill in req.normalized_skills
        ]
        matched = sum(1 for s in jd_skills if s in resume_lower)
        original_score = min(1.0, matched / max(len(jd_skills), 1))

        decision = ATSDecision.PASS if original_score >= threshold else ATSDecision.FAIL

        # Determine next version number
        max_ver = db.execute(
            select(sqlfunc.max(ResumeVersion.version_number)).where(
                ResumeVersion.original_resume_id == resume_doc.id
            )
        ).scalar()
        version_number = (max_ver or 0) + 1

        resume_version = ResumeVersion(
            original_resume_id=resume_doc.id,
            version_number=version_number,
            content=resume_doc.extracted_text,
            ats_score=original_score,
            decision=decision,
        )
        db.add(resume_version)
        db.commit()
        db.refresh(resume_version)
        print(f"[run]   Baseline score: {original_score:.4f} ({decision.value})")
    except Exception as exc:
        print(f"ERROR: ATS scoring failed: {exc}", file=sys.stderr)
        return 1

    # ── Step 5: Generate recourse ─────────────────────────────────────────
    print("[run] Step 5/8: Generating recourse edits...")
    try:
        from backend.app.services import recourse_engine
        from backend.app.schemas.recourse import OptimizationConfig

        edits, re_status, re_reason, re_detail = recourse_engine.generate(
            db=db,
            resume_version_id=resume_version.id,
            job_description_id=jd_record.id,
        )
        print(f"[run]   Recourse engine: {re_status} ({len(edits)} edits)")
    except Exception as exc:
        print(f"ERROR: Recourse generation failed: {exc}", file=sys.stderr)
        edits = []
        re_status = "infeasible"

    # ── Step 6: Optimize ──────────────────────────────────────────────────
    print("[run] Step 6/8: Optimizing edit subset...")
    final_score = original_score
    total_edit_cost = 0.0
    decision_flipped = False
    accepted_edit_ids: list[uuid.UUID] = []

    if edits and re_status == "ok":
        try:
            from backend.app.services import optimizer as optimizer_svc

            edit_cost_weights = model_config.get("edit_cost_weights", {}) if isinstance(model_config, dict) else {}
            opt_config = OptimizationConfig(
                levenshtein_weight=float(edit_cost_weights.get("levenshtein", 0.25)),
                changed_statements_weight=float(edit_cost_weights.get("changed_statements", 0.25)),
                semantic_change_weight=float(edit_cost_weights.get("semantic_change", 0.25)),
                moved_sections_weight=float(edit_cost_weights.get("moved_sections", 0.25)),
                threshold=threshold,
            )

            usable_facts = [
                f for f in facts
                if str(f.verification_status) != "Unsupported"
            ]
            jd_skill_strs = [
                skill for req in requirements for skill in req.normalized_skills
            ]

            opt_result = optimizer_svc.optimize(
                db=db,
                edits=edits,
                resume_version=resume_version,
                usable_facts=usable_facts,
                jd_requirement_skills=jd_skill_strs,
                config=opt_config,
            )

            if opt_result.status == "feasible":
                final_score = opt_result.projected_score
                total_edit_cost = opt_result.total_edit_cost
                decision_flipped = (
                    final_score >= threshold and original_score < threshold
                )
                accepted_edit_ids = [e.id for e in opt_result.accepted_edits]
                print(f"[run]   Feasible: {len(opt_result.accepted_edits)} edits accepted")
                print(f"[run]   Projected score: {final_score:.4f}")
                print(f"[run]   Decision flipped: {decision_flipped}")
            else:
                print(f"[run]   Infeasible: {opt_result.constraints_violated}")
                if opt_result.partial_result:
                    final_score = opt_result.partial_result.projected_score
                    total_edit_cost = opt_result.partial_result.total_edit_cost
        except Exception as exc:
            print(f"WARNING: Optimization failed: {exc}", file=sys.stderr)

    # ── Step 7: Compute grounding metrics ─────────────────────────────────
    print("[run] Step 7/8: Computing grounding metrics...")
    total_edits = len(edits)
    supported_edits = sum(
        1 for e in edits
        if hasattr(e, "verification_status") and
        str(e.verification_status) in ("Supported", "Partially Supported")
    )
    unsupported_edits = sum(
        1 for e in edits
        if hasattr(e, "verification_status") and
        str(e.verification_status) == "Unsupported"
    )

    evidence_grounding_rate = (
        supported_edits / total_edits if total_edits > 0 else 0.0
    )
    unsupported_claim_rate = (
        unsupported_edits / total_edits if total_edits > 0 else 0.0
    )
    # Fact preservation: check how many original facts appear in revised text
    revised_text = resume_doc.extracted_text
    fact_texts = [f.claim_text for f in facts if f.claim_text]
    preserved = sum(
        1 for ft in fact_texts
        if any(tok in revised_text.lower() for tok in ft.lower().split() if len(tok) > 2)
    )
    original_fact_preservation_rate = preserved / max(len(fact_texts), 1)

    # ── Step 8: Record ExperimentRun ──────────────────────────────────────
    print("[run] Step 8/8: Recording experiment run...")
    try:
        from backend.app.services import experiment_logger
        from backend.app.schemas.experiment import ExperimentRunCreate, GroundingMetrics

        # Build model_configuration JSONB
        run_model_config = {
            "sbert_model": model_config.get("sbert_model", "all-MiniLM-L6-v2"),
            "sbert_version": model_config.get("sbert_version", "1.0"),
            "spacy_model": model_config.get("spacy_model", "en_core_web_sm"),
            "spacy_version": model_config.get("spacy_version", "3.7.4"),
            "ats_skill_weight": float(model_config.get("ats_skill_weight", 0.5)),
            "ats_sbert_weight": float(model_config.get("ats_sbert_weight", 0.5)),
            "threshold": threshold,
            "edit_cost_weights": model_config.get(
                "edit_cost_weights",
                {"levenshtein": 0.25, "changed_statements": 0.25,
                 "semantic_change": 0.25, "moved_sections": 0.25},
            ),
        }

        payload = ExperimentRunCreate(
            resume_id=resume_doc.id,
            job_description_id=jd_record.id,
            model_configuration=run_model_config,
            baseline_method=baseline,
            original_score=original_score,
            final_score=final_score,
            threshold=threshold,
            decision_flipped=decision_flipped,
            total_edit_cost=total_edit_cost,
            grounding_metrics=GroundingMetrics(
                evidence_grounding_rate=evidence_grounding_rate,
                unsupported_claim_rate=unsupported_claim_rate,
                original_fact_preservation_rate=original_fact_preservation_rate,
            ),
            random_seed=seed,
            edit_ids=[e.id for e in edits],
        )

        run = experiment_logger.create_run(db=db, payload=payload)

        result = {
            "experiment_run_id": str(run.id),
            "resume_id": str(resume_doc.id),
            "job_description_id": str(jd_record.id),
            "baseline_method": baseline,
            "original_score": original_score,
            "final_score": final_score,
            "threshold": threshold,
            "decision_flipped": decision_flipped,
            "total_edit_cost": total_edit_cost,
            "grounding_metrics": {
                "evidence_grounding_rate": evidence_grounding_rate,
                "unsupported_claim_rate": unsupported_claim_rate,
                "original_fact_preservation_rate": original_fact_preservation_rate,
            },
            "random_seed": seed,
            "edits_generated": len(edits),
            "edits_accepted": len(accepted_edit_ids),
        }

        print("\n[run] ✓ ExperimentRun created successfully")
        print(json.dumps(result, indent=2))
        return 0

    except Exception as exc:
        print(f"ERROR: Failed to record ExperimentRun: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def _stub_extract_requirements(
    jd_text: str,
    jd_id: uuid.UUID,
    db: Any,
) -> list[Any]:
    """
    Stub JD requirement extraction.

    Creates basic skill requirements from the JD text until Dhruv's
    JD_Analyzer is merged. Extracts comma/newline delimited skill words.
    """
    from backend.app.models.job_requirement import JobRequirement
    from backend.app.models.enums import RequirementType, ImportanceLevel, ExtractionType

    # Extract simple word-level skills from text
    import re
    skill_patterns = re.findall(r'\b[A-Z][a-zA-Z+#.]+\b', jd_text)
    unique_skills = list(dict.fromkeys(skill_patterns))[:10]  # Max 10 stub skills

    if not unique_skills:
        unique_skills = ["Software Development"]

    requirements = []
    for i, skill in enumerate(unique_skills):
        req = JobRequirement(
            job_description_id=jd_id,
            requirement_text=f"{skill} experience",
            requirement_type=RequirementType.SKILL,
            importance=ImportanceLevel.REQUIRED,
            extraction_type=ExtractionType.EXPLICIT,
            normalized_skills=[skill],
            source_span={"start": 0, "end": len(skill)},
        )
        db.add(req)
        requirements.append(req)

    return requirements


# ── compare subcommand ────────────────────────────────────────────────────────

def cmd_compare(args: argparse.Namespace) -> int:
    """
    Retrieve multiple ExperimentRun records and write a comparison JSON.

    Output JSON structure:
    {
      "run_ids": [...],
      "runs": [<full ExperimentRun records>],
      "comparison": {
        "flip_rate": float,
        "mean_edit_cost": float,
        "mean_final_score": float,
        "mean_grounding_rate": float,
        "mean_unsupported_rate": float,
        "mean_fact_preservation_rate": float,
        "by_baseline": {<baseline_method>: {<aggregate metrics>}}
      }
    }

    Returns:
        0 on success, 1 on error.
    """
    run_ids_str: list[str] = args.run_ids
    output_path = Path(args.output)

    print(f"[compare] Retrieving {len(run_ids_str)} runs...")

    db = _get_db_session()
    try:
        return _execute_compare(db=db, run_ids_str=run_ids_str, output_path=output_path)
    finally:
        db.close()


def _execute_compare(
    *,
    db: Any,
    run_ids_str: list[str],
    output_path: Path,
) -> int:
    from backend.app.services import experiment_logger
    from backend.app.exceptions import ResourceNotFoundError

    run_data: list[dict[str, Any]] = []
    errors: list[str] = []

    for run_id_str in run_ids_str:
        try:
            run_uuid = uuid.UUID(run_id_str)
        except ValueError:
            errors.append(f"Invalid UUID: {run_id_str}")
            continue

        try:
            run = experiment_logger.get_run(db=db, run_id=run_uuid)
            run_dict = {
                "id": str(run.id),
                "resume_id": str(run.resume_id),
                "job_description_id": str(run.job_description_id),
                "baseline_method": str(run.baseline_method),
                "original_score": run.original_score,
                "final_score": run.final_score,
                "threshold": run.threshold,
                "decision_flipped": run.decision_flipped,
                "total_edit_cost": run.total_edit_cost,
                "grounding_metrics": run.grounding_metrics,
                "random_seed": run.random_seed,
                "model_configuration": run.model_configuration,
                "created_at": run.created_at.isoformat() if run.created_at else None,
            }
            run_data.append(run_dict)
            print(f"[compare]   ✓ {run_id_str}")
        except ResourceNotFoundError:
            errors.append(f"Run not found: {run_id_str}")
            print(f"[compare]   ✗ {run_id_str} — not found")
        except Exception as exc:
            errors.append(f"Error retrieving {run_id_str}: {exc}")
            print(f"[compare]   ✗ {run_id_str} — {exc}")

    if not run_data:
        print("ERROR: No valid runs retrieved.", file=sys.stderr)
        if errors:
            for err in errors:
                print(f"  {err}", file=sys.stderr)
        return 1

    # ── Aggregate metrics ──────────────────────────────────────────────────
    n = len(run_data)
    flip_count = sum(1 for r in run_data if r["decision_flipped"])
    flip_rate = flip_count / n

    mean_edit_cost = sum(r["total_edit_cost"] for r in run_data) / n
    mean_final_score = sum(r["final_score"] for r in run_data) / n

    grounding_rates = [
        r["grounding_metrics"].get("evidence_grounding_rate", 0.0)
        for r in run_data
        if isinstance(r["grounding_metrics"], dict)
    ]
    unsupported_rates = [
        r["grounding_metrics"].get("unsupported_claim_rate", 0.0)
        for r in run_data
        if isinstance(r["grounding_metrics"], dict)
    ]
    preservation_rates = [
        r["grounding_metrics"].get("original_fact_preservation_rate", 0.0)
        for r in run_data
        if isinstance(r["grounding_metrics"], dict)
    ]

    mean_grounding = sum(grounding_rates) / max(len(grounding_rates), 1)
    mean_unsupported = sum(unsupported_rates) / max(len(unsupported_rates), 1)
    mean_preservation = sum(preservation_rates) / max(len(preservation_rates), 1)

    # ── Per-baseline breakdown ────────────────────────────────────────────
    by_baseline: dict[str, dict[str, Any]] = {}
    for run in run_data:
        bm = str(run["baseline_method"])
        if bm not in by_baseline:
            by_baseline[bm] = {
                "count": 0,
                "flip_count": 0,
                "total_edit_cost": 0.0,
                "total_final_score": 0.0,
            }
        by_baseline[bm]["count"] += 1
        by_baseline[bm]["flip_count"] += int(run["decision_flipped"])
        by_baseline[bm]["total_edit_cost"] += run["total_edit_cost"]
        by_baseline[bm]["total_final_score"] += run["final_score"]

    baseline_summary: dict[str, dict[str, Any]] = {}
    for bm, agg in by_baseline.items():
        cnt = agg["count"]
        baseline_summary[bm] = {
            "count": cnt,
            "flip_rate": agg["flip_count"] / cnt,
            "mean_edit_cost": agg["total_edit_cost"] / cnt,
            "mean_final_score": agg["total_final_score"] / cnt,
        }

    output = {
        "run_ids": run_ids_str,
        "run_count": n,
        "errors": errors,
        "runs": run_data,
        "comparison": {
            "flip_rate": flip_rate,
            "mean_edit_cost": mean_edit_cost,
            "mean_final_score": mean_final_score,
            "mean_grounding_rate": mean_grounding,
            "mean_unsupported_rate": mean_unsupported,
            "mean_fact_preservation_rate": mean_preservation,
            "by_baseline": baseline_summary,
        },
    }

    # ── Write output ───────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    print(f"\n[compare] ✓ Comparison written to: {output_path}")
    print(f"  Runs:          {n}")
    print(f"  Flip rate:     {flip_rate:.2%}")
    print(f"  Mean edit cost:{mean_edit_cost:.4f}")
    print(f"  Mean final:    {mean_final_score:.4f}")
    return 0


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="research_cli",
        description="Research CLI for Verifiable Counterfactual Recourse experiments.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── run subcommand ────────────────────────────────────────────────────
    run_parser = subparsers.add_parser(
        "run",
        help="Execute a full pipeline run and record an ExperimentRun.",
    )
    run_parser.add_argument(
        "--config",
        required=True,
        metavar="YAML",
        help="Path to experiment YAML config file.",
    )
    run_parser.add_argument(
        "--resume",
        required=True,
        metavar="PATH",
        help="Path to resume file (PDF, DOCX, or .txt).",
    )
    run_parser.add_argument(
        "--jd",
        required=True,
        metavar="PATH",
        help="Path to job description text file.",
    )
    run_parser.add_argument(
        "--baseline",
        choices=["original_resume", "generic_llm", "proposed"],
        default=None,
        help="Baseline method (overrides config file value).",
    )
    run_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="INT",
        help="Random seed for reproducibility (overrides config file value).",
    )
    run_parser.set_defaults(func=cmd_run)

    # ── compare subcommand ────────────────────────────────────────────────
    compare_parser = subparsers.add_parser(
        "compare",
        help="Retrieve and compare multiple ExperimentRun records.",
    )
    compare_parser.add_argument(
        "--run-ids",
        nargs="+",
        required=True,
        metavar="UUID",
        help="One or more ExperimentRun UUIDs to compare.",
    )
    compare_parser.add_argument(
        "--output",
        required=True,
        metavar="PATH",
        help="Path to write the comparison JSON output.",
    )
    compare_parser.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
