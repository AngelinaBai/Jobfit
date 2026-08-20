from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from jobfit.models import Base, Job, JobSource
from jobfit.services.browser_import import import_browser_job


def test_browser_import_creates_and_updates_without_duplicates():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job, created = import_browser_job(
            session,
            title="Quantitative Analyst Intern",
            company="Example Capital",
            location="New York, NY",
            description="Python and statistics",
            job_url="https://example.com/jobs/123#details",
            platform="linkedin",
        )
        assert created is True
        updated, created_again = import_browser_job(
            session,
            title="Quantitative Analyst Intern",
            company="Example Capital",
            location="New York, NY",
            description="Python, SQL, and statistics",
            job_url="https://example.com/jobs/123#apply",
            platform="linkedin",
        )
        assert created_again is False
        assert updated.id == job.id
        assert session.scalar(select(JobSource.source_type)) == "browser_import"
        assert len(session.scalars(select(Job)).all()) == 1
