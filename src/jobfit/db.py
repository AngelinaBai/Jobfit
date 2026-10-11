from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def normalize_database_url(database_url: str) -> str:
    """Use the installed Psycopg 3 driver for provider-style PostgreSQL URLs."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url


def build_engine(database_url: str, *, echo: bool = False) -> Engine:
    engine = create_engine(
        normalize_database_url(database_url), echo=echo, pool_pre_ping=True
    )
    if engine.dialect.name == "postgresql":
        @event.listens_for(engine, "begin")
        def set_schema(connection):
            # Transaction poolers can reuse sessions with altered settings
            # (for example pg_dump's empty search_path). Pin our schema for
            # every transaction, including transactions on reused connections.
            connection.exec_driver_sql("SET LOCAL search_path TO public")
    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
