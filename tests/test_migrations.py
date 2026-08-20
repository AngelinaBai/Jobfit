from sqlalchemy import create_engine, inspect, text

from jobfit.migrations import apply_migrations


def test_migration_adds_dismissed_to_existing_jobs_table() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE job_sources ("
                "id INTEGER PRIMARY KEY, source_type VARCHAR(50), source_identifier VARCHAR(2048))"
            )
        )
        connection.execute(text("CREATE TABLE jobs (id INTEGER PRIMARY KEY)"))

    apply_migrations(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
    assert "dismissed" in columns

    # The migration must remain safe to run every time the application starts.
    apply_migrations(engine)
