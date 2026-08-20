from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from jobfit.connectors.base import NormalizedJob
from jobfit.models import JobSource, SourceType


class ScanVerificationError(RuntimeError):
    pass


_PLACEHOLDER_TITLES = {
    "careers",
    "jobs",
    "open jobs",
    "open roles",
    "career opportunities",
    "build the future of trading.",
    "paths with purpose",
}


def _canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def verify_scan_jobs(source: JobSource, jobs: list[NormalizedJob]) -> list[NormalizedJob]:
    """Return only credible, deduplicated job records or reject a suspicious scan."""
    verified: dict[str, NormalizedJob] = {}
    source_url = _canonical_url(source.source_identifier)

    for job in jobs:
        title = " ".join(job.title.lower().split())
        job_url = _canonical_url(job.job_url)
        if not job.external_job_id.strip() or not job.title.strip():
            continue
        if not job_url.startswith(("http://", "https://")):
            continue
        if title in _PLACEHOLDER_TITLES:
            continue
        if source.source_type == SourceType.CAREER_PAGE.value and job_url == source_url:
            continue
        verified.setdefault(job.external_job_id, job)

    if jobs and not verified:
        raise ScanVerificationError(
            f"Verification rejected all {len(jobs)} extracted record(s); "
            "the page returned navigation or career-page content instead of job openings."
        )
    return list(verified.values())
