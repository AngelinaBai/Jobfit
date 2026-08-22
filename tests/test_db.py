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
