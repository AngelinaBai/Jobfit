from datetime import UTC, datetime

from jobfit.models import Job
from jobfit.services.filtering import JobFilter, classify_seniority, filter_jobs_in_memory


def make_job(title: str) -> Job:
    return Job(
        id=1,
        external_job_id="1",
        source_id=1,
        title=title,
        company="Example",
        location="New York, NY",
        description="",
        job_url="https://example.com",
        date_posted=None,
        date_discovered=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        content_hash="a" * 64,
        status="active",
    )


def test_seniority_classifier() -> None:
    assert classify_seniority("Data Science Intern") == "intern"
    assert classify_seniority("Senior Quantitative Researcher") == "senior"
    assert classify_seniority("Quantitative Analyst") == "entry"
    assert classify_seniority("Research Engineer") == "unknown"


def test_entry_filter_excludes_explicit_senior_roles() -> None:
    jobs = [make_job("Quantitative Analyst"), make_job("Senior Data Scientist")]
    result = filter_jobs_in_memory(jobs, JobFilter(seniority="entry"))
    assert [job.title for job in result] == ["Quantitative Analyst"]
