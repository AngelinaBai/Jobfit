from __future__ import annotations

from sqlalchemy import Engine, inspect, text


def apply_migrations(engine: Engine) -> None:
    """Apply small idempotent migrations needed before a full migration tool is introduced."""
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(
                text(
                    "ALTER TABLE job_sources ALTER COLUMN source_identifier TYPE VARCHAR(2048)"
                )
            )
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_job_sources_type_identifier
                ON job_sources (source_type, source_identifier)
                """
            )
        )
        columns = {column["name"] for column in inspect(connection).get_columns("jobs")}
        if "dismissed" not in columns:
            connection.execute(
                text("ALTER TABLE jobs ADD COLUMN dismissed BOOLEAN NOT NULL DEFAULT FALSE")
            )
