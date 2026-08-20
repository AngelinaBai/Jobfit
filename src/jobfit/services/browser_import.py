from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobfit.models import Job, JobStatus
from jobfit.services.sources import get_or_create_browser_source


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def import_browser_job(
    session: Session,
    *,
    title: str,
    company: str,
    location: str | None,
    description: str,
    job_url: str,
    platform: str,
) -> tuple[Job, bool]:
    title = title.strip()
    company = company.strip()
    job_url = canonicalize_url(job_url)
    if not title or not company or not job_url.startswith(("http://", "https://")):
        raise ValueError("Title, company, and a valid job URL are required")
    source = get_or_create_browser_source(session, platform)
    external_id = hashlib.sha256(job_url.encode("utf-8")).hexdigest()[:32]
    content = "|".join([title, company, location or "", description or "", job_url])
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    existing = session.scalar(
        select(Job).where(Job.source_id == source.id, Job.external_job_id == external_id)
    )
    now = datetime.now(UTC)
    if existing:
        existing.title = title
        existing.company = company
        existing.location = location.strip() if location else None
        existing.description = description.strip()
        existing.job_url = job_url
        existing.content_hash = content_hash
        existing.last_seen_at = now
        existing.status = JobStatus.ACTIVE.value
        session.commit()
        session.refresh(existing)
        return existing, False

    job = Job(
        external_job_id=external_id,
        source_id=source.id,
        title=title,
        company=company,
        location=location.strip() if location else None,
        description=description.strip(),
        job_url=job_url,
        date_posted=None,
        date_discovered=now,
        last_seen_at=now,
        content_hash=content_hash,
        status=JobStatus.ACTIVE.value,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job, True
