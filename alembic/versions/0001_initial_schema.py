"""Initial schema — all domain model tables

Revision ID: 0001
Revises:
Create Date: 2026-10-02

Creates:
  - resume_documents
  - candidate_facts         (FK → resume_documents ON DELETE CASCADE)
  - job_descriptions
  - job_requirements        (FK → job_descriptions ON DELETE CASCADE)
  - resume_versions         (UNIQUE(original_resume_id, version_number))
  - proposed_edits          (FK → resume_versions ON DELETE CASCADE)
  - proposed_edit_facts     (junction)
  - proposed_edit_requirements (junction)
  - experiment_runs
  - experiment_run_edits    (junction)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── resume_documents ──────────────────────────────────────────────────────
    op.create_table(
        "resume_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column(
            "document_type",
            sa.String(10),
            sa.CheckConstraint("document_type IN ('pdf','docx','manual')",
                               name="ck_resume_documents_document_type"),
            nullable=False,
        ),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("source_spans", postgresql.JSONB(), nullable=False,
                  server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_resume_documents"),
    )
    op.create_index("ix_resume_documents_candidate_id",
                    "resume_documents", ["candidate_id"])

    # ── candidate_facts ───────────────────────────────────────────────────────
    op.create_table(
        "candidate_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("original_claim_text", sa.Text(), nullable=False),
        sa.Column(
            "claim_type",
            sa.String(20),
            sa.CheckConstraint(
                "claim_type IN ('skill','project','responsibility','certification',"
                "'experience','achievement')",
                name="ck_candidate_facts_claim_type",
            ),
            nullable=False,
        ),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_span", postgresql.JSONB(), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(30),
            sa.CheckConstraint(
                "verification_status IN ('Supported','Partially Supported',"
                "'Unsupported','Needs Confirmation')",
                name="ck_candidate_facts_verification_status",
            ),
            nullable=False,
            server_default="Needs Confirmation",
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False,
                  server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_candidate_facts"),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["resume_documents.id"],
            name="fk_candidate_facts_source_document",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_candidate_facts_candidate_id",
                    "candidate_facts", ["candidate_id"])
    op.create_index("ix_candidate_facts_source_document_id",
                    "candidate_facts", ["source_document_id"])

    # ── job_descriptions ──────────────────────────────────────────────────────
    op.create_table(
        "job_descriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_job_descriptions"),
    )

    # ── job_requirements ──────────────────────────────────────────────────────
    op.create_table(
        "job_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_description_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column(
            "requirement_type",
            sa.String(20),
            sa.CheckConstraint(
                "requirement_type IN ('skill','certification','experience',"
                "'qualification','responsibility')",
                name="ck_job_requirements_requirement_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "importance",
            sa.String(10),
            sa.CheckConstraint("importance IN ('required','preferred')",
                               name="ck_job_requirements_importance"),
            nullable=False,
            server_default="required",
        ),
        sa.Column(
            "extraction_type",
            sa.String(10),
            sa.CheckConstraint("extraction_type IN ('explicit','inferred')",
                               name="ck_job_requirements_extraction_type"),
            nullable=False,
        ),
        sa.Column("normalized_skills", postgresql.JSONB(), nullable=False,
                  server_default="[]"),
        sa.Column("source_span", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_job_requirements"),
        sa.ForeignKeyConstraint(
            ["job_description_id"], ["job_descriptions.id"],
            name="fk_job_requirements_job_description",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_job_requirements_job_description_id",
                    "job_requirements", ["job_description_id"])

    # ── resume_versions ───────────────────────────────────────────────────────
    op.create_table(
        "resume_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("original_resume_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("ats_score", sa.Float(), nullable=True),
        sa.Column(
            "decision",
            sa.String(4),
            sa.CheckConstraint("decision IN ('pass','fail')",
                               name="ck_resume_versions_decision"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_resume_versions"),
        sa.UniqueConstraint(
            "original_resume_id", "version_number",
            name="uq_resume_versions_resume_version",
        ),
        sa.ForeignKeyConstraint(
            ["original_resume_id"], ["resume_documents.id"],
            name="fk_resume_versions_resume_document",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_resume_versions_original_resume_id",
                    "resume_versions", ["original_resume_id"])

    # ── proposed_edits ────────────────────────────────────────────────────────
    op.create_table(
        "proposed_edits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("resume_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("proposed_text", sa.Text(), nullable=False),
        sa.Column(
            "edit_type",
            sa.String(30),
            sa.CheckConstraint(
                "edit_type IN ('rephrase','surface_qualification','reorder',"
                "'normalize_terminology','reorganize_sections','remove_redundancy')",
                name="ck_proposed_edits_edit_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "verification_status",
            sa.String(30),
            sa.CheckConstraint(
                "verification_status IN ('Supported','Partially Supported',"
                "'Unsupported','Needs Confirmation')",
                name="ck_proposed_edits_verification_status",
            ),
            nullable=False,
            server_default="Needs Confirmation",
        ),
        sa.Column("edit_cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("score_contribution", sa.Float(), nullable=False,
                  server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_proposed_edits"),
        sa.ForeignKeyConstraint(
            ["resume_version_id"], ["resume_versions.id"],
            name="fk_proposed_edits_resume_version",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_proposed_edits_resume_version_id",
                    "proposed_edits", ["resume_version_id"])

    # ── proposed_edit_facts (junction) ────────────────────────────────────────
    op.create_table(
        "proposed_edit_facts",
        sa.Column("proposed_edit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_fact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("proposed_edit_id", "candidate_fact_id",
                                name="pk_proposed_edit_facts"),
        sa.ForeignKeyConstraint(
            ["proposed_edit_id"], ["proposed_edits.id"],
            name="fk_pef_proposed_edit", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_fact_id"], ["candidate_facts.id"],
            name="fk_pef_candidate_fact", ondelete="CASCADE",
        ),
    )

    # ── proposed_edit_requirements (junction) ─────────────────────────────────
    op.create_table(
        "proposed_edit_requirements",
        sa.Column("proposed_edit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_requirement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("proposed_edit_id", "job_requirement_id",
                                name="pk_proposed_edit_requirements"),
        sa.ForeignKeyConstraint(
            ["proposed_edit_id"], ["proposed_edits.id"],
            name="fk_per_proposed_edit", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_requirement_id"], ["job_requirements.id"],
            name="fk_per_job_requirement", ondelete="CASCADE",
        ),
    )

    # ── experiment_runs ───────────────────────────────────────────────────────
    op.create_table(
        "experiment_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("resume_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_description_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_configuration", postgresql.JSONB(), nullable=False),
        sa.Column(
            "baseline_method",
            sa.String(20),
            sa.CheckConstraint(
                "baseline_method IN ('original_resume','generic_llm','proposed')",
                name="ck_experiment_runs_baseline_method",
            ),
            nullable=False,
        ),
        sa.Column("original_score", sa.Float(), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("decision_flipped", sa.Boolean(), nullable=False),
        sa.Column("total_edit_cost", sa.Float(), nullable=False),
        sa.Column("grounding_metrics", postgresql.JSONB(), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_experiment_runs"),
        sa.ForeignKeyConstraint(
            ["resume_id"], ["resume_documents.id"],
            name="fk_experiment_runs_resume",
        ),
        sa.ForeignKeyConstraint(
            ["job_description_id"], ["job_descriptions.id"],
            name="fk_experiment_runs_job_description",
        ),
    )

    # ── experiment_run_edits (junction) ───────────────────────────────────────
    op.create_table(
        "experiment_run_edits",
        sa.Column("experiment_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposed_edit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("experiment_run_id", "proposed_edit_id",
                                name="pk_experiment_run_edits"),
        sa.ForeignKeyConstraint(
            ["experiment_run_id"], ["experiment_runs.id"],
            name="fk_ere_experiment_run", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_edit_id"], ["proposed_edits.id"],
            name="fk_ere_proposed_edit", ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("experiment_run_edits")
    op.drop_table("experiment_runs")
    op.drop_table("proposed_edit_requirements")
    op.drop_table("proposed_edit_facts")
    op.drop_table("proposed_edits")
    op.drop_table("resume_versions")
    op.drop_table("job_requirements")
    op.drop_table("job_descriptions")
    op.drop_table("candidate_facts")
    op.drop_table("resume_documents")
