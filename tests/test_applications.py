from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobfit.models import ApplicationStatus, Base, Job, JobSource
from jobfit.services.applications import add_manual_application, list_applications, set_application_status


def make_job(session: Session) -> Job:
    source = JobSource(
        company_name="Example",
        source_type="greenhouse",
        source_identifier="example",
        enabled=True,
    )
    session.add(source)
    session.flush()
    job = Job(
        external_job_id="1",
        source_id=source.id,
        title="Data Analyst",
        company="Example",
        location="New York, NY",
        description="Description",
        job_url="https://example.com/job/1",
        date_posted=datetime.now(timezone.utc),
        date_discovered=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        content_hash="a" * 64,
        status="active",
    )
    session.add(job)
    session.commit()
    return job


def test_mark_applied_creates_tracker_record(session: Session) -> None:
    job = make_job(session)
    application = set_application_status(
        session,
        job_id=job.id,
        status=ApplicationStatus.APPLIED.value,
        notes="Applied through company site",
        resume_version="quant-v2.pdf",
    )
    assert application.status == "applied"
    assert application.applied_at is not None
    assert application.notes == "Applied through company site"
    assert application.resume_version == "quant-v2.pdf"


def test_update_status_reuses_same_record(session: Session) -> None:
    job = make_job(session)
    first = set_application_status(session, job_id=job.id, status="saved")
    second = set_application_status(session, job_id=job.id, status="interview")
    assert first.id == second.id
    assert second.status == "interview"
    assert len(list_applications(session)) == 1


def test_manual_application_creates_hidden_job_and_tracker_record(session: Session) -> None:
    application = add_manual_application(
        session,
        title="Quantitative Analyst",
        company="Manual Co",
        location="New York, NY",
        job_url="https://manual.example/job/123",
        status="applied",
        source_label="LinkedIn",
        resume_version="tech.pdf",
    )
    assert application.status == "applied"
    assert application.job.title == "Quantitative Analyst"
    assert application.job.status == "inactive"
    assert application.job.source.source_identifier == "manual-linkedin"
    assert application.resume_version == "tech.pdf"


def test_manual_application_reuses_existing_job_by_url(session: Session) -> None:
    job = make_job(session)
    application = add_manual_application(
        session,
        title="Different typed title",
        company="Example",
        job_url=job.job_url,
        status="applied",
        source_label="Company Website",
    )
    assert application.job_id == job.id
    assert application.job.status == "active"


def test_manual_application_job_remains_available_after_session_closes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        application = add_manual_application(
            session,
            title="Algorithm Researcher",
            company="Example Trading",
            status="applied",
        )

    assert application.job.company == "Example Trading"
    assert application.job.title == "Algorithm Researcher"
