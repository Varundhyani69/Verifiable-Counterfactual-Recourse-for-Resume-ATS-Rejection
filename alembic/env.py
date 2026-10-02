"""
Alembic environment script.

Reads DATABASE_URL from the environment so that no credentials are stored
in source control. Uses SQLAlchemy's synchronous engine for migrations.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Import all ORM models so Alembic can detect them for autogenerate.
# Add new model imports here as each teammate implements their module.
# ---------------------------------------------------------------------------
from backend.app.database import Base  # noqa: F401 — populates Base.metadata

# Individual model imports (uncomment as each module is implemented):
# from backend.app.models.resume_document import ResumeDocument          # Varun / Task 2
# from backend.app.models.candidate_fact import CandidateFact            # Varun / Task 2
# from backend.app.models.job_description import JobDescription          # Varun / Task 2
# from backend.app.models.job_requirement import JobRequirement          # Varun / Task 2
# from backend.app.models.resume_version import ResumeVersion            # Varun / Task 2
# from backend.app.models.proposed_edit import ProposedEdit              # Varun / Task 2
# from backend.app.models.experiment_run import ExperimentRun            # Varun / Task 2

# ---------------------------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Override sqlalchemy.url with the DATABASE_URL env var so credentials
# never end up in alembic.ini.
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://user:password@localhost:5432/recourse_db"
)
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
