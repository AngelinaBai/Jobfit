from __future__ import annotations

import argparse

from sqlalchemy import select

from jobfit.config import Settings
from jobfit.db import build_engine, build_session_factory
from jobfit.logging_config import configure_logging
from jobfit.models import Job, JobStatus
from jobfit.services.matching import SponsorshipAssessment, score_job


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank jobs against Angelina Bai's resume profile")
    parser.add_argument("--min-score", type=int, default=45)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument(
        "--sponsorship",
        choices=("any", "compatible", "not-incompatible", "unknown"),
        default="not-incompatible",
        help="Posting-text visa filter; unknown does not mean employer acceptance",
    )
    parser.add_argument(
        "--all-locations",
        action="store_true",
        help="Include jobs outside the preferred U.S./China/Singapore regions.",
    )
    return parser.parse_args()


def _passes_sponsorship(value: SponsorshipAssessment, requested: str) -> bool:
    if requested == "any":
        return True
    if requested == "compatible":
        return value == SponsorshipAssessment.LIKELY_COMPATIBLE
    if requested == "unknown":
        return value == SponsorshipAssessment.UNKNOWN
    return value != SponsorshipAssessment.LIKELY_NOT_COMPATIBLE


def main() -> None:
    args = parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        jobs = list(
            session.scalars(
                select(Job)
                .where(Job.status == JobStatus.ACTIVE.value)
                .order_by(Job.date_discovered.desc())
            ).all()
        )

    ranked: list[tuple[Job, object]] = []
    for job in jobs:
        result = score_job(job)
        if result.score < args.min_score or not result.eligible:
            continue
        if not args.all_locations and result.location_region not in {"us", "china", "singapore", "unknown"}:
            continue
        if result.location_region == "us" and not _passes_sponsorship(result.sponsorship, args.sponsorship):
            continue
        ranked.append((job, result))

    ranked.sort(key=lambda item: (item[1].score, item[0].date_discovered), reverse=True)
    ranked = ranked[: args.limit]

    if not ranked:
        print("No personalized matches found for the selected filters.")
        return

    print(f"Found {len(ranked)} personalized match(es).")
    print("Visa label is based only on posting text; verify with the employer before relying on it.\n")
    for job, result in ranked:
        location = job.location or "Location not listed"
        print(f"[{job.id}] {result.score}/100 | {job.title}")
        print(f"    {job.company} | {location}")
        print(f"    Seniority: {result.seniority} | Region: {result.location_region} | OPT/F-1: {result.sponsorship.value if result.location_region == 'us' else 'n/a'}")
        if result.reasons:
            print("    Why it fits: " + "; ".join(result.reasons[:3]))
        if result.concerns:
            print("    Check: " + "; ".join(result.concerns[:2]))
        print(f"    {job.job_url}\n")


if __name__ == "__main__":
    main()
