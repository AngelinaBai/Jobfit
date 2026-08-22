from __future__ import annotations

import os
import base64
import secrets
import webbrowser
from datetime import UTC, date, datetime, timezone
from pathlib import Path
from typing import Annotated
from urllib.parse import quote_plus

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from jobfit.config import Settings
from jobfit.connectors.factory import build_connector
from jobfit.db import build_engine, build_session_factory
from jobfit.migrations import apply_migrations
from jobfit.models import Application, ApplicationStatus, Base, Job, JobSource, ScanRun
from jobfit.services.applications import add_manual_application, set_application_status
from jobfit.services.browser_import import import_browser_job
from jobfit.services.career_discovery import discover_career_source
from jobfit.services.filtering import matches_terms
from jobfit.services.ingestion import ingest_verified_jobs, scan_source
from jobfit.services.matching import SponsorshipAssessment, score_job
from jobfit.services.sources import (
    DEFAULT_SOURCES,
    add_source,
    delete_source_preserving_applications,
    set_source_enabled,
    update_source,
)
from jobfit.services.source_onboarding import verify_source_candidate

PACKAGE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="JobFit", version="0.9.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"chrome-extension://.*|moz-extension://.*|http://127\.0\.0\.1(:\d+)?|http://localhost(:\d+)?",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")

settings = Settings.from_env()
engine = build_engine(settings.database_url)
SessionFactory = build_session_factory(engine)
Base.metadata.create_all(engine)
apply_migrations(engine)

PRIVATE_GET_PATHS = {"/applications", "/safari"}


def _has_admin_credentials(request: Request) -> bool:
    if not settings.public_mode:
        return True
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Basic ") or not settings.admin_password:
        return False
    try:
        decoded = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False
    return secrets.compare_digest(username, settings.admin_username) and secrets.compare_digest(
        password, settings.admin_password
    )


@app.middleware("http")
async def protect_private_features(request: Request, call_next):
    private_get = request.method == "GET" and request.url.path in PRIVATE_GET_PATHS
    write_request = request.method not in {"GET", "HEAD", "OPTIONS"}
    if settings.public_mode and (private_get or write_request) and not _has_admin_credentials(request):
        return PlainTextResponse(
            "Administrator authentication required.",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="JobFit Admin"'},
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/healthz", include_in_schema=False)
def healthcheck() -> JSONResponse:
    with SessionFactory() as session:
        session.execute(select(1))
    return JSONResponse({"status": "ok"})


def _parse_terms(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _get_dashboard_jobs(
    *,
    query: str | None,
    location: str | None,
    sponsorship: str,
    region: str,
    eligibility: str,
    min_score: int,
    status: str,
    limit: int,
    sort_mode: str,
    keyword_scope: str,
    career_track: str,
) -> list[dict]:
    query_terms = _parse_terms(query)
    location_terms = _parse_terms(location)

    with SessionFactory() as session:
        statement = (
            select(Job)
            .options(joinedload(Job.application))
            .where(Job.status == "active", Job.dismissed.is_(False))
            .order_by(Job.date_discovered.desc())
        )
        # Provider-hosted PostgreSQL is network-bound. Apply conservative SQL
        # supersets first, then retain the exact word-boundary checks below.
        if query_terms and keyword_scope == "title":
            statement = statement.where(
                or_(*(Job.title.ilike(f"%{term}%") for term in query_terms))
            )
        if location_terms:
            statement = statement.where(
                or_(*(Job.location.ilike(f"%{term}%") for term in location_terms))
            )

        jobs = list(
            session.scalars(
                statement.limit(10000)
            ).unique().all()
        )

    rows: list[dict] = []
    hidden_statuses = {
        ApplicationStatus.APPLIED.value,
        ApplicationStatus.ASSESSMENT.value,
        ApplicationStatus.INTERVIEW.value,
        ApplicationStatus.OFFER.value,
        ApplicationStatus.REJECTED.value,
        ApplicationStatus.WITHDRAWN.value,
    }

    for job in jobs:
        # Once an application moves beyond Saved, it belongs to Applications,
        # not the discovery/search workflow.
        if job.application and job.application.status in hidden_statuses:
            continue

        result = score_job(job)
        if career_track != "all" and result.career_track.value != career_track:
            continue
        searchable = f"{job.title} {job.company} {job.description}" if keyword_scope == "all" else job.title
        location_text = job.location or ""

        if not matches_terms(searchable, query_terms):
            continue
        if not matches_terms(location_text, location_terms):
            continue
        if result.score < min_score:
            continue
        if eligibility == "eligible" and not result.eligible:
            continue
        if eligibility == "excluded" and result.eligible:
            continue
        if region == "preferred" and result.location_region not in {"us", "china", "singapore", "unknown"}:
            continue
        if region in {"us", "china", "singapore"} and result.location_region != region:
            continue

        if result.location_region == "us":
            if sponsorship == "compatible" and result.sponsorship != SponsorshipAssessment.LIKELY_COMPATIBLE:
                continue
            if sponsorship == "not-incompatible" and result.sponsorship == SponsorshipAssessment.LIKELY_NOT_COMPATIBLE:
                continue
            if sponsorship == "unknown" and result.sponsorship != SponsorshipAssessment.UNKNOWN:
                continue
            if sponsorship == "incompatible" and result.sponsorship != SponsorshipAssessment.LIKELY_NOT_COMPATIBLE:
                continue

        if status != "all":
            current_status = job.application.status if job.application else "untracked"
            if current_status != status:
                continue

        reference_date = job.date_posted or job.date_discovered
        if reference_date.tzinfo is None:
            reference_date = reference_date.replace(tzinfo=UTC)
        age_days = max(0, (datetime.now(UTC) - reference_date).days)
        freshness_boost = 20 if age_days <= 1 else 14 if age_days <= 3 else 8 if age_days <= 7 else 3 if age_days <= 14 else 0
        rows.append({
            "job": job,
            "match": result,
            "application": job.application,
            "age_days": age_days,
            "freshness_boost": freshness_boost,
            "today_priority": result.score + freshness_boost,
        })

    if sort_mode == "today":
        rows.sort(
            key=lambda row: (
                row["today_priority"],
                row["match"].title_seniority_priority,
                row["job"].date_discovered,
            ),
            reverse=True,
        )
    elif sort_mode == "score":
        rows.sort(key=lambda row: (row["match"].score, row["job"].date_discovered), reverse=True)
    else:
        rows.sort(
            key=lambda row: (
                row["match"].title_seniority_priority,
                row["match"].score,
                row["job"].date_discovered,
            ),
            reverse=True,
        )
    return rows[:limit]


def _safari_bookmarklet() -> str:
    js = r'''(function(){
function t(ss){for(const s of ss){const e=document.querySelector(s);const x=(e&&((e.innerText||e.textContent)||'').trim())||'';if(x)return x}return''}
const h=location.hostname.toLowerCase();let p='company-site';if(h.includes('linkedin.com'))p='linkedin';else if(h.includes('joinhandshake.com'))p='handshake';else if(h.includes('12twenty.com'))p='12twenty';
const title=t(['.job-details-jobs-unified-top-card__job-title h1','.job-details-jobs-unified-top-card__job-title','h1']);
const company=t(['.job-details-jobs-unified-top-card__company-name a','.job-details-jobs-unified-top-card__company-name','.jobs-unified-top-card__company-name','[data-hook="employer-name"]','[class*="company-name"]']);
const loc=t(['.job-details-jobs-unified-top-card__primary-description-container','.job-details-jobs-unified-top-card__tertiary-description-container','.jobs-unified-top-card__bullet','[data-hook="job-location"]','[class*="job-location"]']);
const description=t(['#job-details','.jobs-description-content__text','.jobs-box__html-content','[data-hook="job-description"]','[class*="job-description"]','main']);
const f=document.createElement('form');f.method='POST';f.action='http://127.0.0.1:8000/bookmarklet/review';f.target='_blank';
const vals={title:title,company:company,location:loc,description:description,job_url:location.href,platform:p};for(const[k,v]of Object.entries(vals)){const i=document.createElement('input');i.type='hidden';i.name=k;i.value=v||'';f.appendChild(i)}document.body.appendChild(f);f.submit();f.remove();
})()'''
    return "javascript:" + "".join(line.strip() for line in js.splitlines())


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    query: str = Query("quant,data science,machine learning,artificial intelligence,ai,software engineer,software developer,analytics,risk,research"),
    location: str = Query(""),
    sponsorship: str = Query("not-incompatible"),
    region: str = Query("preferred"),
    eligibility: str = Query("eligible"),
    min_score: int = Query(25, ge=0, le=100),
    status: str = Query("all"),
    limit: int = Query(50, ge=1, le=200),
    sort_mode: str = Query("today"),
    keyword_scope: str = Query("title"),
    career_track: str = Query("all"),
    message: str | None = Query(None),
) -> HTMLResponse:
    is_admin = _has_admin_credentials(request)
    rows = _get_dashboard_jobs(
        query=query,
        location=location,
        sponsorship=sponsorship,
        region=region,
        eligibility=eligibility,
        min_score=min_score,
        status=status,
        limit=limit,
        sort_mode=sort_mode,
        keyword_scope=keyword_scope,
        career_track=career_track,
    )

    with SessionFactory() as session:
        metrics = {
            "jobs": session.scalar(select(func.count(Job.id)).where(Job.status == "active")) or 0,
            "sources": session.scalar(select(func.count(JobSource.id)).where(JobSource.enabled.is_(True))) or 0,
            "saved": session.scalar(select(func.count(Application.id)).where(Application.status == ApplicationStatus.SAVED.value)) or 0,
            "applied": session.scalar(select(func.count(Application.id)).where(Application.status == ApplicationStatus.APPLIED.value)) or 0,
            "interviews": session.scalar(select(func.count(Application.id)).where(Application.status == ApplicationStatus.INTERVIEW.value)) or 0,
        }
        metrics["last_refreshed"] = session.scalar(select(func.max(ScanRun.completed_at)))
        sources = (
            list(session.scalars(select(JobSource).order_by(JobSource.company_name)).all())
            if is_admin
            else []
        )
        latest_scans: dict[int, ScanRun] = {}
        if is_admin:
            for scan_run in session.scalars(select(ScanRun).order_by(ScanRun.id.desc())).all():
                latest_scans.setdefault(scan_run.source_id, scan_run)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "rows": rows,
            "metrics": metrics,
            "sources": sources,
            "latest_scans": latest_scans,
            "filters": {
                "query": query,
                "location": location,
                "sponsorship": sponsorship,
                "region": region,
                "eligibility": eligibility,
                "min_score": min_score,
                "status": status,
                "limit": limit,
                "sort_mode": sort_mode,
                "keyword_scope": keyword_scope,
                "career_track": career_track,
            },
            "message": message,
            "statuses": [ApplicationStatus.SAVED.value],
            "public_mode": settings.public_mode,
            "is_admin": is_admin,
        },
    )


@app.get("/applications", response_class=HTMLResponse)
def applications_page(
    request: Request,
    status: str = Query("all"),
    query: str = Query(""),
    message: str | None = Query(None),
) -> HTMLResponse:
    with SessionFactory() as session:
        statement = (
            select(Application)
            .options(joinedload(Application.job).joinedload(Job.source))
            .order_by(Application.updated_at.desc())
        )
        if status != "all":
            statement = statement.where(Application.status == status)
        applications = list(session.scalars(statement).unique().all())

        terms = _parse_terms(query)
        if terms:
            applications = [
                a for a in applications
                if matches_terms(f"{a.job.title} {a.job.company} {a.job.location or ''}", terms)
            ]

        metrics = {
            "total": session.scalar(select(func.count(Application.id))) or 0,
            "applied": session.scalar(select(func.count(Application.id)).where(Application.status == ApplicationStatus.APPLIED.value)) or 0,
            "assessments": session.scalar(select(func.count(Application.id)).where(Application.status == ApplicationStatus.ASSESSMENT.value)) or 0,
            "interviews": session.scalar(select(func.count(Application.id)).where(Application.status == ApplicationStatus.INTERVIEW.value)) or 0,
            "offers": session.scalar(select(func.count(Application.id)).where(Application.status == ApplicationStatus.OFFER.value)) or 0,
            "rejected": session.scalar(select(func.count(Application.id)).where(Application.status == ApplicationStatus.REJECTED.value)) or 0,
        }

    return templates.TemplateResponse(
        request=request,
        name="applications.html",
        context={
            "applications": applications,
            "metrics": metrics,
            "statuses": [item.value for item in ApplicationStatus],
            "filters": {"status": status, "query": query},
            "message": message,
            "today": date.today().isoformat(),
        },
    )


@app.post("/applications/manual")
def create_manual_application(
    title: Annotated[str, Form()],
    company: Annotated[str, Form()],
    status: Annotated[str, Form()] = ApplicationStatus.APPLIED.value,
    location: Annotated[str | None, Form()] = None,
    job_url: Annotated[str | None, Form()] = None,
    applied_date: Annotated[str | None, Form()] = None,
    source_label: Annotated[str, Form()] = "Other",
    resume_version: Annotated[str | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    allowed = {item.value for item in ApplicationStatus}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid application status")
    parsed_date = None
    if applied_date:
        try:
            parsed_date = date.fromisoformat(applied_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid application date") from exc

    with SessionFactory() as session:
        try:
            application = add_manual_application(
                session,
                title=title,
                company=company,
                location=location,
                job_url=job_url,
                status=status,
                applied_date=parsed_date,
                source_label=source_label,
                resume_version=resume_version,
                notes=notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(
        url=f"/applications?message={quote_plus(f'Added {application.job.company} — {application.job.title}.')}",
        status_code=303,
    )


@app.post("/applications/{application_id}/status")
def update_application_status(
    application_id: int,
    status: Annotated[str, Form()],
    notes: Annotated[str | None, Form()] = None,
    resume_version: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    allowed = {item.value for item in ApplicationStatus}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid application status")
    with SessionFactory() as session:
        application = session.get(Application, application_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        set_application_status(
            session,
            job_id=application.job_id,
            status=status,
            notes=(notes or "").strip() or None,
            resume_version=(resume_version or "").strip() or None,
        )
    return RedirectResponse(url=f"/applications?message=Application+updated+to+{status}.", status_code=303)


@app.post("/scan")
def run_scan() -> RedirectResponse:
    inserted = updated = scanned = failures = 0
    with SessionFactory() as session:
        sources = list(
            session.scalars(
                select(JobSource).where(
                    JobSource.enabled.is_(True),
                    JobSource.source_type.in_(["greenhouse", "lever", "ashby", "career_page"]),
                )
            ).all()
        )
        for source in sources:
            try:
                connector = build_connector(source.source_type, timeout_seconds=settings.http_timeout_seconds)
                summary = scan_source(session, source, connector)
                inserted += summary.inserted
                updated += summary.updated
                scanned += summary.jobs_found
            except Exception:
                failures += 1
    message = f"Scan complete: {scanned} found, {inserted} new, {updated} updated, {failures} failures."
    return RedirectResponse(url=f"/?message={quote_plus(message)}", status_code=303)


@app.post("/sources/seed")
def seed_sources() -> RedirectResponse:
    added = 0
    with SessionFactory() as session:
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
    return RedirectResponse(url=f"/?message=Added+{added}+new+starter+source(s).", status_code=303)


@app.post("/sources/add")
def create_source(
    company_name: Annotated[str, Form()],
    source_identifier: Annotated[str, Form()],
    source_type: Annotated[str, Form()] = "greenhouse",
    careers_url: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    with SessionFactory() as session:
        try:
            add_source(
                session,
                company_name=company_name.strip(),
                source_type=source_type.strip().lower(),
                source_identifier=source_identifier.strip(),
                careers_url=(careers_url or "").strip() or None,
            )
            message = f"Added {company_name}."
        except Exception as exc:
            message = str(exc)
    return RedirectResponse(url=f"/?message={quote_plus(message)}", status_code=303)


@app.post("/sources/{source_id}/edit")
def edit_source(
    source_id: int,
    company_name: Annotated[str, Form()],
    source_identifier: Annotated[str, Form()],
    source_type: Annotated[str, Form()],
    careers_url: Annotated[str | None, Form()] = None,
    enabled: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    with SessionFactory() as session:
        try:
            source = update_source(
                session,
                source_id=source_id,
                company_name=company_name,
                source_type=source_type.strip().lower(),
                source_identifier=source_identifier,
                careers_url=careers_url,
                enabled=enabled == "on",
            )
            message = f"Updated {source.company_name}."
        except Exception as exc:
            message = f"Could not update source: {exc}"
    return RedirectResponse(url=f"/?message={quote_plus(message)}", status_code=303)


@app.post("/sources/{source_id}/toggle")
def toggle_source(source_id: int) -> RedirectResponse:
    with SessionFactory() as session:
        source = session.get(JobSource, source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Source not found")
        if source.source_type == "browser_import":
            raise HTTPException(status_code=400, detail="Local sources are managed automatically")
        source = set_source_enabled(session, source_id=source_id, enabled=not source.enabled)
        state = "enabled" if source.enabled else "disabled"
        message = f"{source.company_name} {state}."
    return RedirectResponse(url=f"/?message={quote_plus(message)}", status_code=303)


@app.post("/sources/{source_id}/scan")
def scan_one_source(source_id: int) -> RedirectResponse:
    with SessionFactory() as session:
        source = session.get(JobSource, source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Source not found")
        if source.source_type == "browser_import":
            raise HTTPException(status_code=400, detail="Local sources cannot be scanned")
        try:
            connector = build_connector(
                source.source_type, timeout_seconds=settings.http_timeout_seconds
            )
            summary = scan_source(session, source, connector)
            message = (
                f"{source.company_name}: {summary.jobs_found} found, "
                f"{summary.inserted} new, {summary.updated} updated."
            )
        except Exception as exc:
            message = f"{source.company_name} scan failed: {exc}"
    return RedirectResponse(url=f"/?message={quote_plus(message)}", status_code=303)


@app.post("/sources/{source_id}/delete")
def delete_source(source_id: int) -> RedirectResponse:
    with SessionFactory() as session:
        source = session.get(JobSource, source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Source not found")
        name = source.company_name
        try:
            archived, removed = delete_source_preserving_applications(
                session, source_id=source_id
            )
            message = (
                f"Deleted {name}. Removed {removed} untracked job(s); "
                f"preserved {archived} tracked job(s) in the local archive."
            )
        except Exception as exc:
            message = f"Could not delete {name}: {exc}"
    return RedirectResponse(url=f"/?message={quote_plus(message)}", status_code=303)


@app.post("/sources/discover")
def discover_source(
    company_name: Annotated[str, Form()],
    careers_url: Annotated[str, Form()],
) -> RedirectResponse:
    company = company_name.strip()
    url = careers_url.strip()
    try:
        detection = discover_career_source(url, timeout_seconds=settings.http_timeout_seconds)
        connector = build_connector(
            detection.source_type, timeout_seconds=settings.http_timeout_seconds
        )
        candidate = verify_source_candidate(
            company_name=company,
            detection=detection,
            connector=connector,
        )
        with SessionFactory() as session:
            source, created = add_source(
                session,
                company_name=company,
                source_type=detection.source_type,
                source_identifier=detection.source_identifier,
                careers_url=detection.careers_url,
            )
            summary = ingest_verified_jobs(session, source, list(candidate.jobs))
        action = "Added" if created else "Updated"
        message = f"{action} {company} after verification: {detection.detail}. Confirmed {summary.jobs_found} individual jobs ({summary.inserted} new)."
    except Exception as exc:
        message = f"Could not add {company or 'career page'}: {exc}"
    return RedirectResponse(url=f"/?message={quote_plus(message)}", status_code=303)


@app.get("/safari", response_class=HTMLResponse)
def safari_install(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="safari.html", context={"bookmarklet": _safari_bookmarklet()})


@app.post("/bookmarklet/review", response_class=HTMLResponse)
def bookmarklet_review(
    request: Request,
    title: Annotated[str, Form()] = "",
    company: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    job_url: Annotated[str, Form()] = "",
    platform: Annotated[str, Form()] = "browser",
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="import_review.html",
        context={
            "title": title.strip(),
            "company": company.strip(),
            "location": location.strip(),
            "description": description.strip(),
            "job_url": job_url.strip(),
            "platform": platform.strip() or "browser",
        },
    )


@app.post("/bookmarklet/save")
def bookmarklet_save(
    title: Annotated[str, Form()],
    company: Annotated[str, Form()],
    job_url: Annotated[str, Form()],
    location: Annotated[str | None, Form()] = None,
    description: Annotated[str, Form()] = "",
    platform: Annotated[str, Form()] = "browser",
) -> RedirectResponse:
    with SessionFactory() as session:
        try:
            job, created = import_browser_job(
                session,
                title=title,
                company=company,
                location=(location or "").strip() or None,
                description=description,
                job_url=job_url,
                platform=platform,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    action = "Imported" if created else "Updated"
    return RedirectResponse(url=f"/?query={quote_plus(job.title)}&keyword_scope=title&message={action}+JobFit+%23{job.id}", status_code=303)


@app.post("/api/import-job")
async def import_job(request: Request) -> dict:
    payload = await request.json()
    with SessionFactory() as session:
        try:
            job, created = import_browser_job(
                session,
                title=str(payload.get("title") or ""),
                company=str(payload.get("company") or ""),
                location=str(payload.get("location") or "") or None,
                description=str(payload.get("description") or ""),
                job_url=str(payload.get("job_url") or payload.get("url") or ""),
                platform=str(payload.get("platform") or "browser"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "created": created, "job_id": job.id, "dashboard_url": f"http://127.0.0.1:8000/?query={job.title}"}


@app.post("/jobs/{job_id}/status")
def update_job_status(
    job_id: int,
    status: Annotated[str, Form()],
    notes: Annotated[str | None, Form()] = None,
    resume_version: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    allowed = {item.value for item in ApplicationStatus}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid application status")
    with SessionFactory() as session:
        set_application_status(
            session,
            job_id=job_id,
            status=status,
            notes=(notes or "").strip() or None,
            resume_version=(resume_version or "").strip() or None,
        )
    if status == ApplicationStatus.SAVED.value:
        return RedirectResponse(url=f"/?message=Job+{job_id}+saved.", status_code=303)
    return RedirectResponse(url=f"/applications?message=Moved+job+{job_id}+to+Applications+as+{status}.", status_code=303)


@app.post("/jobs/{job_id}/dismiss")
def dismiss_job(job_id: int) -> RedirectResponse:
    with SessionFactory() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        job.dismissed = True
        title = job.title
        session.commit()
    return RedirectResponse(
        url=f"/?message={quote_plus(f'Removed {title} from job recommendations.')}",
        status_code=303,
    )


@app.get("/jobs/{job_id}/open")
def open_job(job_id: int) -> RedirectResponse:
    with SessionFactory() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if not job.job_url or job.job_url == "about:blank":
            raise HTTPException(status_code=404, detail="No application URL stored")
        return RedirectResponse(url=job.job_url, status_code=302)


def main() -> None:
    import uvicorn

    host = os.getenv("JOBFIT_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("JOBFIT_WEB_PORT", "8000"))
    url = f"http://{host}:{port}"
    print(f"JobFit web dashboard: {url}")
    if os.getenv("JOBFIT_NO_BROWSER", "0") != "1":
        webbrowser.open(url)
    uvicorn.run("jobfit.web:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
