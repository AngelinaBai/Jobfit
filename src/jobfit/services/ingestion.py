from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobfit.connectors.base import JobConnector, NormalizedJob
from jobfit.models import Job, JobSource, JobStatus, ScanRun, ScanStatus
from jobfit.services.scan_verification import verify_scan_jobs

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScanSummary:
    source_id: int
    jobs_found: int
    inserted: int
    updated: int
    unchanged: int


def scan_source(session: Session, source: JobSource, connector: JobConnector) -> ScanSummary:
    started_at = datetime.now(UTC)
    scan_run = ScanRun(
        source_id=source.id,
        started_at=started_at,
        status=ScanStatus.RUNNING.value,
    )
    session.add(scan_run)
    session.commit()

    try:
        fetched_jobs = connector.fetch_jobs(
            source_identifier=source.source_identifier,
            company_name=source.company_name,
        )
        remote_jobs = verify_scan_jobs(source, fetched_jobs)
        summary = _persist_verified_jobs(session, source, scan_run, remote_jobs)

        logger.info(
            "source_scan_succeeded",
            extra={
                "source_id": source.id,
                "jobs_found": summary.jobs_found,
                "inserted": summary.inserted,
                "updated": summary.updated,
                "unchanged": summary.unchanged,
            },
        )
        return summary

    except Exception as exc:
        session.rollback()
        failed_at = datetime.now(UTC)
        persisted_run = session.get(ScanRun, scan_run.id)
        if persisted_run is not None:
            persisted_run.completed_at = failed_at
            persisted_run.status = ScanStatus.FAILED.value
            persisted_run.error_message = str(exc)[:4000]
            session.commit()
        logger.exception("source_scan_failed", extra={"source_id": source.id})
        raise


def ingest_verified_jobs(
    session: Session,
    source: JobSource,
    jobs: list[NormalizedJob],
) -> ScanSummary:
    """Persist a candidate source's already-fetched, verified onboarding results."""
    verified = verify_scan_jobs(source, jobs)
    if not verified:
        raise ValueError("A source cannot be added until at least one real job is verified.")
    scan_run = ScanRun(
        source_id=source.id,
        started_at=datetime.now(UTC),
        status=ScanStatus.RUNNING.value,
    )
    session.add(scan_run)
    session.flush()
    return _persist_verified_jobs(session, source, scan_run, verified)


def _persist_verified_jobs(
    session: Session,
    source: JobSource,
    scan_run: ScanRun,
    remote_jobs: list[NormalizedJob],
) -> ScanSummary:
    now = datetime.now(UTC)
    inserted = updated = unchanged = 0
    for remote_job in remote_jobs:
        result = _upsert_job(session, source, remote_job, now)
        if result == "inserted":
            inserted += 1
        elif result == "updated":
            updated += 1
        else:
            unchanged += 1

    source.last_scanned_at = now
    scan_run.completed_at = now
    scan_run.jobs_found = len(remote_jobs)
    scan_run.new_jobs_added = inserted
    scan_run.jobs_updated = updated
    scan_run.jobs_unchanged = unchanged
    scan_run.status = ScanStatus.VERIFIED.value
    session.commit()
    return ScanSummary(source.id, len(remote_jobs), inserted, updated, unchanged)


def _upsert_job(
    session: Session,
    source: JobSource,
    remote: NormalizedJob,
    observed_at: datetime,
) -> str:
    existing = session.scalar(
        select(Job).where(
            Job.source_id == source.id,
            Job.external_job_id == remote.external_job_id,
        )
    )

    if existing is None:
        session.add(
            Job(
                external_job_id=remote.external_job_id,
                source_id=source.id,
                title=remote.title,
                company=remote.company,
                location=remote.location,
                description=remote.description,
                job_url=remote.job_url,
                date_posted=remote.date_posted,
                date_discovered=observed_at,
                last_seen_at=observed_at,
                content_hash=remote.content_hash,
                status=JobStatus.ACTIVE.value,
            )
        )
        return "inserted"

    existing.last_seen_at = observed_at
    existing.status = JobStatus.ACTIVE.value

    if existing.content_hash == remote.content_hash:
        return "unchanged"

    existing.title = remote.title
    existing.company = remote.company
    existing.location = remote.location
    existing.description = remote.description
    existing.job_url = remote.job_url
    existing.date_posted = remote.date_posted
    existing.content_hash = remote.content_hash
    return "updated"
