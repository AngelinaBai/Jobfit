from jobfit.db import build_engine, normalize_database_url


def test_neon_postgresql_url_uses_psycopg3_driver():
    url = "postgresql://jobfit:secret@example.neon.tech/neondb?sslmode=require"
    normalized = normalize_database_url(url)

    assert normalized.startswith("postgresql+psycopg://")
    engine = build_engine(url)
    assert engine.url.drivername == "postgresql+psycopg"


def test_legacy_provider_postgres_url_uses_psycopg3_driver():
    assert normalize_database_url("postgres://user:secret@host/database") == (
        "postgresql+psycopg://user:secret@host/database"
    )


def test_explicit_database_driver_is_preserved():
    url = "postgresql+psycopg://user:secret@host/database"
    assert normalize_database_url(url) == url


def test_postgresql_transactions_recover_from_empty_search_path():
    """Exercise real PostgreSQL transaction reuse without modifying user tables."""
    import os
    import pytest

    url = os.getenv("JOBFIT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set JOBFIT_TEST_POSTGRES_URL for PostgreSQL integration coverage")
    engine = build_engine(url)
    with engine.connect() as connection:
        # Simulate a session returned by a backup client/transaction pooler.
        connection.exec_driver_sql("SET SESSION search_path TO ''")
        connection.commit()
        for _ in range(2):
            assert connection.exec_driver_sql("SHOW search_path").scalar_one() == "public"
            assert connection.exec_driver_sql("SELECT to_regclass('jobs')").scalar_one() == "jobs"
            connection.rollback()
        connection.exec_driver_sql("RESET search_path")
        connection.commit()
    engine.dispose()
