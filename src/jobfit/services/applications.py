from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobfit.models import Application, ApplicationStatus, Job, JobSource, JobStatus, SourceType


def get_job(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} was not found.")
    return job


def set_application_status(
    session: Session,
    *,
    job_id: int,
    status: str,
    notes: str | None = None,
    resume_version: str | None = None,
    applied_at: datetime | None = None,
) -> Application:
    job = get_job(session, job_id)
    application = session.scalar(select(Application).where(Application.job_id == job.id))
    now = datetime.now(timezone.utc)

    if application is None:
        application = Application(job_id=job.id, status=status)
        session.add(application)

    application.status = status
    application.updated_at = now
    if notes is not None:
        application.notes = notes
    if resume_version is not None:
        application.resume_version = resume_version

    if applied_at is not None:
        application.applied_at = applied_at
    elif status == ApplicationStatus.APPLIED.value and application.applied_at is None:
        application.applied_at = now

    session.commit()
    # Load the related job while the application is still attached. FastAPI
    # builds redirect messages after the request-scoped session closes, so an
    # unloaded relationship here would raise DetachedInstanceError.
    session.refresh(application, attribute_names=["job"])
    return application


def _manual_source(session: Session, source_label: str = "Other") -> JobSource:
    label = (source_label or "Other").strip() or "Other"
    identifier = "manual-" + "".join(ch.lower() if ch.isalnum() else "-" for ch in label).strip("-")
    source = session.scalar(
        select(JobSource).where(
            JobSource.source_type == SourceType.BROWSER_IMPORT.value,
            JobSource.source_identifier == identifier,
        )
    )
    if source is None:
        source = JobSource(
            company_name=f"Manual: {label}",
            source_type=SourceType.BROWSER_IMPORT.value,
            source_identifier=identifier,
            careers_url=None,
            enabled=False,
        )
        session.add(source)
        session.flush()
    return source


def add_manual_application(
    session: Session,
    *,
    title: str,
    company: str,
    location: str | None = None,
    job_url: str | None = None,
    status: str = ApplicationStatus.APPLIED.value,
    applied_date: date | None = None,
    resume_version: str | None = None,
    notes: str | None = None,
    source_label: str = "Other",
) -> Application:
    """Add an application even when JobFit did not discover the posting.

    If the supplied URL already belongs to a discovered Job, reuse that Job.
    Otherwise create a hidden/inactive Job record so the application can still use
    the existing tracker model without surfacing on the discovery page.
    """
    clean_title = title.strip()
    clean_company = company.strip()
    clean_url = (job_url or "").strip()
    if not clean_title or not clean_company:
        raise ValueError("Job title and company are required.")

    job: Job | None = None
    if clean_url:
        job = session.scalar(select(Job).where(Job.job_url == clean_url).limit(1))

    if job is None:
        source = _manual_source(session, source_label)
        stable = clean_url or f"{clean_company}|{clean_title}|{location or ''}"
        external_id = "manual-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
        job = session.scalar(
            select(Job).where(Job.source_id == source.id, Job.external_job_id == external_id)
        )
        if job is None:
            now = datetime.now(timezone.utc)
            content = f"{clean_title}|{clean_company}|{location or ''}|{clean_url}"
            job = Job(
                external_job_id=external_id,
                source_id=source.id,
                title=clean_title,
                company=clean_company,
                location=(location or "").strip() or None,
                description="Manually added application.",
                job_url=clean_url or "about:blank",
                date_posted=None,
                date_discovered=now,
                last_seen_at=now,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                status=JobStatus.INACTIVE.value,
            )
            session.add(job)
            session.flush()

    applied_at = None
    if applied_date:
        applied_at = datetime.combine(applied_date, time.min, tzinfo=timezone.utc)

    return set_application_status(
        session,
        job_id=job.id,
        status=status,
        notes=(notes or "").strip() or None,
        resume_version=(resume_version or "").strip() or None,
        applied_at=applied_at,
    )


def list_applications(session: Session, *, status: str | None = None) -> list[Application]:
    statement = select(Application).join(Application.job).order_by(Application.updated_at.desc())
    if status:
        statement = statement.where(Application.status == status)
    return list(session.scalars(statement).all())
