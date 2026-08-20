from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from jobfit.models import Application, Job, JobSource, ScanRun, SourceType


@dataclass(frozen=True, slots=True)
class SeedSource:
    company_name: str
    source_type: str
    source_identifier: str
    careers_url: str


DEFAULT_SOURCES = (
    SeedSource("Anthropic", SourceType.GREENHOUSE.value, "anthropic", "https://job-boards.greenhouse.io/anthropic"),
    SeedSource("Stripe", SourceType.GREENHOUSE.value, "stripe", "https://job-boards.greenhouse.io/stripe"),
    SeedSource("Databricks", SourceType.GREENHOUSE.value, "databricks", "https://job-boards.greenhouse.io/databricks"),
    SeedSource("Scale AI", SourceType.GREENHOUSE.value, "scaleai", "https://job-boards.greenhouse.io/scaleai"),
)
DEFAULT_GREENHOUSE_SOURCES = DEFAULT_SOURCES


def add_source(
    session: Session,
    *,
    company_name: str,
    source_identifier: str,
    careers_url: str | None,
    source_type: str = SourceType.GREENHOUSE.value,
) -> tuple[JobSource, bool]:
    if source_type not in {item.value for item in SourceType if item != SourceType.BROWSER_IMPORT}:
        raise ValueError(f"Unsupported source type: {source_type}")
    raw_identifier = source_identifier.strip()
    normalized_identifier = (
        raw_identifier.lower()
        if source_type in {SourceType.GREENHOUSE.value, SourceType.LEVER.value}
        else raw_identifier
    )
    existing = session.scalar(
        select(JobSource).where(
            JobSource.source_type == source_type,
            JobSource.source_identifier == normalized_identifier,
        )
    )
    if existing is not None:
        existing.company_name = company_name.strip()
        existing.careers_url = careers_url
        existing.enabled = True
        session.commit()
        return existing, False

    source = JobSource(
        company_name=company_name.strip(),
        source_type=source_type,
        source_identifier=normalized_identifier,
        careers_url=careers_url,
        enabled=True,
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return source, True


def get_or_create_browser_source(session: Session, platform: str) -> JobSource:
    normalized = (platform or "browser").strip().lower()[:255]
    existing = session.scalar(
        select(JobSource).where(
            JobSource.source_type == SourceType.BROWSER_IMPORT.value,
            JobSource.source_identifier == normalized,
        )
    )
    if existing:
        return existing
    source = JobSource(
        company_name=f"{normalized.title()} imports",
        source_type=SourceType.BROWSER_IMPORT.value,
        source_identifier=normalized,
        careers_url=None,
        enabled=False,
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def seed_default_sources(session: Session) -> tuple[int, int]:
    added = existing = 0
    for source in DEFAULT_SOURCES:
        _, created = add_source(
            session,
            company_name=source.company_name,
            source_type=source.source_type,
            source_identifier=source.source_identifier,
            careers_url=source.careers_url,
        )
        if created:
            added += 1
        else:
            existing += 1
    return added, existing


def update_source(
    session: Session,
    *,
    source_id: int,
    company_name: str,
    source_type: str,
    source_identifier: str,
    careers_url: str | None,
    enabled: bool,
) -> JobSource:
    source = session.get(JobSource, source_id)
    if source is None:
        raise ValueError("Source not found")

    allowed = {item.value for item in SourceType if item != SourceType.BROWSER_IMPORT}
    if source_type not in allowed:
        raise ValueError(f"Unsupported source type: {source_type}")

    company = company_name.strip()
    raw_identifier = source_identifier.strip()
    if not company:
        raise ValueError("Company name is required")
    if not raw_identifier:
        raise ValueError("Source identifier is required")
    normalized_identifier = (
        raw_identifier.lower()
        if source_type in {SourceType.GREENHOUSE.value, SourceType.LEVER.value}
        else raw_identifier
    )

    duplicate = session.scalar(
        select(JobSource).where(
            JobSource.id != source_id,
            JobSource.source_type == source_type,
            JobSource.source_identifier == normalized_identifier,
        )
    )
    if duplicate is not None:
        raise ValueError("Another source already uses that type and identifier")

    source.company_name = company
    source.source_type = source_type
    source.source_identifier = normalized_identifier
    source.careers_url = (careers_url or "").strip() or None
    source.enabled = bool(enabled)
    session.commit()
    session.refresh(source)
    return source


def set_source_enabled(session: Session, *, source_id: int, enabled: bool) -> JobSource:
    source = session.get(JobSource, source_id)
    if source is None:
        raise ValueError("Source not found")
    source.enabled = enabled
    session.commit()
    session.refresh(source)
    return source


def delete_source_preserving_applications(session: Session, *, source_id: int) -> tuple[int, int]:
    """Delete a monitored source while preserving jobs with application records."""
    source = session.get(JobSource, source_id)
    if source is None:
        raise ValueError("Source not found")
    if source.source_type == SourceType.BROWSER_IMPORT.value:
        raise ValueError("Local import and archive sources cannot be deleted")

    jobs = list(session.scalars(select(Job).where(Job.source_id == source_id)).all())
    tracked_ids = set(
        session.scalars(
            select(Application.job_id).where(
                Application.job_id.in_([job.id for job in jobs] or [-1])
            )
        ).all()
    )
    tracked_jobs = [job for job in jobs if job.id in tracked_ids]
    untracked_jobs = [job for job in jobs if job.id not in tracked_ids]

    if tracked_jobs:
        archive = session.scalar(
            select(JobSource).where(
                JobSource.source_type == SourceType.BROWSER_IMPORT.value,
                JobSource.source_identifier == "archived",
            )
        )
        if archive is None:
            archive = JobSource(
                company_name="Archived tracked jobs",
                source_type=SourceType.BROWSER_IMPORT.value,
                source_identifier="archived",
                careers_url=None,
                enabled=False,
            )
            session.add(archive)
            session.flush()

        for job in tracked_jobs:
            job.external_job_id = f"archived:{source.id}:{job.external_job_id}"[:255]
            job.source_id = archive.id

    session.flush()
    if untracked_jobs:
        session.execute(delete(Job).where(Job.id.in_([job.id for job in untracked_jobs])))
    session.execute(delete(ScanRun).where(ScanRun.source_id == source_id))
    session.execute(delete(JobSource).where(JobSource.id == source_id))
    session.commit()
    return len(tracked_jobs), len(untracked_jobs)
