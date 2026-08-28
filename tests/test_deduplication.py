from __future__ import annotations

from jobfit.models import Job
from jobfit.services.deduplication import job_duplicate_keys


def _job(**overrides: object) -> Job:
    values: dict[str, object] = {
        "external_job_id": "job-1",
        "source_id": 1,
        "title": "Quantitative Trader",
        "company": "Example Capital",
        "location": "New York, NY",
        "description": "Research and trade systematic strategies.",
        "job_url": "https://www.example.com/jobs/123?utm_source=board",
        "content_hash": "a" * 64,
    }
    values.update(overrides)
    return Job(**values)


def test_duplicate_keys_match_tracking_url_variants() -> None:
    tracked = _job()
    rediscovered = _job(
        external_job_id="replacement-id",
        job_url="http://example.com/jobs/123/?gh_src=campaign#apply",
    )

    assert job_duplicate_keys(tracked) & job_duplicate_keys(rediscovered)


def test_duplicate_keys_match_same_normalized_role_at_same_location() -> None:
    tracked = _job(job_url="https://ats-one.example/opening/123")
    rediscovered = _job(
        external_job_id="other-source-id",
        title="  QUANTITATIVE   TRADER ",
        company="Example Capital!",
        location="New York, NY.",
        job_url="https://ats-two.example/roles/abc",
    )

    assert job_duplicate_keys(tracked) & job_duplicate_keys(rediscovered)


def test_duplicate_keys_keep_same_title_in_different_locations_distinct() -> None:
    new_york = _job(job_url="https://example.com/jobs/new-york")
    chicago = _job(
        external_job_id="job-2",
        location="Chicago, IL",
        job_url="https://example.com/jobs/chicago",
    )

    assert not (job_duplicate_keys(new_york) & job_duplicate_keys(chicago))
