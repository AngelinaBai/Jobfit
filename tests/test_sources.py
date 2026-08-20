from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from datetime import datetime, timezone

import pytest

from jobfit.models import Application, Base, Job, JobSource
from jobfit.services.sources import (
    add_source,
    delete_source_preserving_applications,
    seed_default_sources,
    set_source_enabled,
    update_source,
)


def test_add_source_is_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first, created_first = add_source(
            session,
            company_name="Anthropic",
            source_identifier="anthropic",
            careers_url="https://job-boards.greenhouse.io/anthropic",
        )
        second, created_second = add_source(
            session,
            company_name="Anthropic",
            source_identifier="ANTHROPIC",
            careers_url="https://job-boards.greenhouse.io/anthropic",
        )
        assert created_first is True
        assert created_second is False
        assert first.id == second.id
        assert session.query(JobSource).count() == 1


def test_seed_default_sources_can_run_twice() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert seed_default_sources(session) == (4, 0)
        assert seed_default_sources(session) == (0, 4)


def test_update_and_toggle_source() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source, _ = add_source(
            session,
            company_name="Anthropic",
            source_identifier="anthropic",
            careers_url="https://old.example",
        )
        updated = update_source(
            session,
            source_id=source.id,
            company_name="Anthropic AI",
            source_type="greenhouse",
            source_identifier="ANTHROPIC-NEW",
            careers_url="https://new.example",
            enabled=False,
        )
        assert updated.company_name == "Anthropic AI"
        assert updated.source_identifier == "anthropic-new"
        assert updated.careers_url == "https://new.example"
        assert updated.enabled is False
        assert set_source_enabled(session, source_id=source.id, enabled=True).enabled is True


def test_update_source_rejects_duplicate_identifier() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first, _ = add_source(
            session, company_name="First", source_identifier="first", careers_url=None
        )
        add_source(
            session, company_name="Second", source_identifier="second", careers_url=None
        )
        with pytest.raises(ValueError, match="Another source"):
            update_source(
                session,
                source_id=first.id,
                company_name="First",
                source_type="greenhouse",
                source_identifier="second",
                careers_url=None,
                enabled=True,
            )


def test_delete_source_preserves_tracked_jobs() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source, _ = add_source(
            session,
            company_name="Example",
            source_identifier="example",
            careers_url="https://example.com/jobs",
        )
        now = datetime.now(timezone.utc)
        tracked = Job(
            external_job_id="1", source_id=source.id, title="Data Analyst",
            company="Example", location="NY", description="desc",
            job_url="https://example.com/1", date_posted=None,
            date_discovered=now, last_seen_at=now,
            content_hash="a" * 64, status="active",
        )
        untracked = Job(
            external_job_id="2", source_id=source.id, title="Other",
            company="Example", location="NY", description="desc",
            job_url="https://example.com/2", date_posted=None,
            date_discovered=now, last_seen_at=now,
            content_hash="b" * 64, status="active",
        )
        session.add_all([tracked, untracked])
        session.flush()
        application = Application(job_id=tracked.id, status="applied")
        session.add(application)
        session.commit()

        archived, removed = delete_source_preserving_applications(
            session, source_id=source.id
        )
        assert (archived, removed) == (1, 1)
        preserved_job = session.get(Job, tracked.id)
        assert preserved_job is not None
        assert preserved_job.source.source_identifier == "archived"
        assert session.get(Application, application.id) is not None
        assert session.get(Job, untracked.id) is None
        assert session.get(JobSource, source.id) is None


def test_delete_rejects_local_import_source() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = JobSource(
            company_name="Browser imports",
            source_type="browser_import",
            source_identifier="browser",
            enabled=False,
        )
        session.add(source)
        session.commit()
        with pytest.raises(ValueError, match="Local import"):
            delete_source_preserving_applications(session, source_id=source.id)
