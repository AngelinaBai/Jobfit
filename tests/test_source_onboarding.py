from datetime import UTC, datetime

import pytest

from jobfit.connectors.base import NormalizedJob
from jobfit.services.career_discovery import CareerSourceDetection
from jobfit.services.scan_verification import ScanVerificationError
from jobfit.services.source_onboarding import (
    SourceVerificationInconclusive,
    verify_source_candidate,
)


class StubConnector:
    def __init__(self, jobs):
        self.jobs = jobs

    def fetch_jobs(self, *, source_identifier: str, company_name: str):
        return self.jobs


DETECTION = CareerSourceDetection(
    source_type="greenhouse",
    source_identifier="example",
    careers_url="https://example.com/careers",
    detail="Detected Greenhouse",
)


def real_job() -> NormalizedJob:
    return NormalizedJob(
        external_job_id="123",
        title="Data Scientist, New Grad",
        company="Example",
        location="New York, NY",
        description="Python and SQL",
        job_url="https://example.com/jobs/123",
        date_posted=datetime(2026, 8, 14, tzinfo=UTC),
        content_hash="a" * 64,
    )


def test_candidate_requires_at_least_one_verified_individual_job() -> None:
    with pytest.raises(SourceVerificationInconclusive, match="not added"):
        verify_source_candidate(
            company_name="Example",
            detection=DETECTION,
            connector=StubConnector([]),
        )


def test_candidate_rejects_navigation_content() -> None:
    placeholder = real_job()
    placeholder = NormalizedJob(
        external_job_id=placeholder.external_job_id,
        title="Open roles",
        company=placeholder.company,
        location=placeholder.location,
        description=placeholder.description,
        job_url=placeholder.job_url,
        date_posted=placeholder.date_posted,
        content_hash=placeholder.content_hash,
    )
    with pytest.raises(ScanVerificationError, match="rejected all"):
        verify_source_candidate(
            company_name="Example",
            detection=DETECTION,
            connector=StubConnector([placeholder]),
        )


def test_candidate_returns_verified_jobs_for_persistence() -> None:
    candidate = verify_source_candidate(
        company_name="Example",
        detection=DETECTION,
        connector=StubConnector([real_job()]),
    )
    assert len(candidate.jobs) == 1
    assert candidate.jobs[0].external_job_id == "123"
