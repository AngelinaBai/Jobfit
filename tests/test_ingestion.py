from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobfit.connectors.base import NormalizedJob
from jobfit.models import Job, JobSource, ScanRun, ScanStatus, SourceType
from jobfit.services.ingestion import ingest_verified_jobs, scan_source
from jobfit.services.scan_verification import ScanVerificationError


class StubConnector:
    def __init__(self, jobs: list[NormalizedJob]) -> None:
        self.jobs = jobs

    def fetch_jobs(self, *, source_identifier: str, company_name: str) -> list[NormalizedJob]:
        return self.jobs


def make_job(*, content_hash: str = "a" * 64, title: str = "Quant Analyst") -> NormalizedJob:
    return NormalizedJob(
        external_job_id="123",
        title=title,
        company="Example Capital",
        location="New York, NY",
        description="Analyze data",
        job_url="https://example.com/jobs/123",
        date_posted=datetime(2026, 8, 6, tzinfo=UTC),
        content_hash=content_hash,
    )


def make_source(session: Session) -> JobSource:
    source = JobSource(
        company_name="Example Capital",
        source_type=SourceType.GREENHOUSE.value,
        source_identifier="example",
        careers_url="https://example.com/careers",
        enabled=True,
    )
    session.add(source)
    session.commit()
    return source


def test_scan_inserts_new_job_and_scan_run(session: Session) -> None:
    source = make_source(session)

    summary = scan_source(session, source, StubConnector([make_job()]))

    assert summary.inserted == 1
    assert summary.updated == 0
    stored_job = session.scalar(select(Job))
    assert stored_job is not None
    assert stored_job.external_job_id == "123"
    scan_run = session.scalar(select(ScanRun))
    assert scan_run.status == ScanStatus.VERIFIED.value
    assert scan_run.new_jobs_added == 1


def test_second_identical_scan_is_unchanged(session: Session) -> None:
    source = make_source(session)
    connector = StubConnector([make_job()])
    scan_source(session, source, connector)
    first_seen = session.scalar(select(Job)).last_seen_at

    summary = scan_source(session, source, connector)

    assert summary.unchanged == 1
    assert session.scalar(select(Job)).last_seen_at >= first_seen


def test_changed_hash_updates_existing_job(session: Session) -> None:
    source = make_source(session)
    scan_source(session, source, StubConnector([make_job()]))

    summary = scan_source(
        session,
        source,
        StubConnector([make_job(content_hash="b" * 64, title="Senior Quant Analyst")]),
    )

    assert summary.updated == 1
    jobs = session.scalars(select(Job)).all()
    assert len(jobs) == 1
    assert jobs[0].title == "Senior Quant Analyst"


def test_failure_is_recorded(session: Session) -> None:
    source = make_source(session)

    class FailingConnector:
        def fetch_jobs(self, *, source_identifier: str, company_name: str):
            raise RuntimeError("remote failure")

    try:
        scan_source(session, source, FailingConnector())
    except RuntimeError:
        pass

    scan_run = session.scalar(select(ScanRun))
    assert scan_run.status == ScanStatus.FAILED.value
    assert "remote failure" in scan_run.error_message


def test_suspicious_career_page_result_fails_verification(session: Session) -> None:
    source = make_source(session)
    suspicious = make_job(title="Build the future of trading.")

    with pytest.raises(ScanVerificationError, match="Verification rejected"):
        scan_source(session, source, StubConnector([suspicious]))

    assert session.scalar(select(Job)) is None
    scan_run = session.scalar(select(ScanRun))
    assert scan_run.status == ScanStatus.FAILED.value
    assert "navigation or career-page content" in scan_run.error_message


def test_ingest_verified_onboarding_jobs_without_refetch(session: Session) -> None:
    source = make_source(session)
    summary = ingest_verified_jobs(session, source, [make_job()])
    assert summary.jobs_found == 1
    assert summary.inserted == 1
    assert session.scalar(select(ScanRun)).status == ScanStatus.VERIFIED.value
