from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from jobfit.config import Settings
from jobfit.connectors.factory import build_connector
from jobfit.db import build_engine, build_session_factory
from jobfit.logging_config import configure_logging
from jobfit.migrations import apply_migrations
from jobfit.models import Base, Job, JobSource, SourceType
from jobfit.services.matching import SponsorshipAssessment, score_job
from jobfit.services.ingestion import scan_source

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan enabled JobFit job sources")
    parser.add_argument("--create-tables", action="store_true")
    parser.add_argument(
        "--show-new",
        action="store_true",
        help="Print jobs first discovered during this scan",
    )
    return parser.parse_args()


def _print_new_jobs(jobs: list[Job]) -> None:
    ranked = []
    for job in jobs:
        result = score_job(job)
        if result.score < 45 or not result.eligible:
            continue
        if result.location_region not in {"us", "china", "singapore", "unknown"}:
            continue
        if result.location_region == "us" and result.sponsorship == SponsorshipAssessment.LIKELY_NOT_COMPATIBLE:
            continue
        ranked.append((job, result))

    ranked.sort(key=lambda item: item[1].score, reverse=True)
    print(
        f"\nNew jobs discovered: {len(jobs)} total; "
        f"{len(ranked)} eligible matches in U.S./China/Singapore\n"
    )
    for job, result in ranked:
        print(f"[{job.id}] {result.score}/100 | {job.title}")
        print(f"    {job.company} | {job.location or 'Location not listed'}")
        print(f"    OPT/F-1: {result.sponsorship.value}")
        if result.reasons:
            print(f"    Why it fits: {'; '.join(result.reasons[:2])}")
        print(f"    {job.job_url}\n")


def main() -> None:
    args = parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    engine = build_engine(settings.database_url)
    if args.create_tables:
        Base.metadata.create_all(engine)
        apply_migrations(engine)

    session_factory = build_session_factory(engine)
    batch_started_at = datetime.now(UTC)

    with session_factory() as session:
        sources = session.scalars(
            select(JobSource).where(
                JobSource.enabled.is_(True),
                JobSource.source_type.in_([SourceType.GREENHOUSE.value, SourceType.LEVER.value, SourceType.ASHBY.value, SourceType.CAREER_PAGE.value]),
            )
        ).all()

        logger.info("scan_batch_started", extra={"source_count": len(sources)})
        failures = 0
        for source in sources:
            try:
                connector = build_connector(source.source_type, timeout_seconds=settings.http_timeout_seconds)
                scan_source(session, source, connector)
            except Exception:
                failures += 1

        logger.info("scan_batch_completed", extra={"source_count": len(sources), "failures": failures})

        if args.show_new:
            jobs = list(
                session.scalars(
                    select(Job)
                    .where(Job.date_discovered >= batch_started_at)
                    .order_by(Job.date_discovered.desc())
                ).all()
            )
            _print_new_jobs(jobs)

        if failures:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
