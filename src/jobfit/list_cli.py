from __future__ import annotations

import argparse

from jobfit.config import Settings
from jobfit.db import build_engine, build_session_factory
from jobfit.logging_config import configure_logging
from jobfit.services.filtering import (
    DEFAULT_TITLE_KEYWORDS,
    JobFilter,
    build_job_query,
    filter_jobs_in_memory,
    split_keywords,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List filtered JobFit postings")
    parser.add_argument(
        "--title",
        help="Comma-separated title keywords",
        default=",".join(DEFAULT_TITLE_KEYWORDS),
    )
    parser.add_argument(
        "--location",
        help="Comma-separated location keywords; omit to allow all locations",
    )
    parser.add_argument(
        "--seniority",
        choices=("all", "intern", "entry", "mid", "senior"),
        default="entry",
    )
    parser.add_argument("--since-hours", type=int, help="Only jobs first discovered this recently")
    parser.add_argument("--limit", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    filters = JobFilter(
        title_keywords=split_keywords(args.title),
        location_keywords=split_keywords(args.location),
        seniority=args.seniority,
        since_hours=args.since_hours,
        limit=max(args.limit * 4, args.limit),
    )

    with session_factory() as session:
        candidates = list(session.scalars(build_job_query(filters)).all())
        jobs = filter_jobs_in_memory(candidates, filters)[: args.limit]

    if not jobs:
        print("No matching jobs found.")
        return

    print(f"Found {len(jobs)} matching job(s):\n")
    for job in jobs:
        location = job.location or "Location not listed"
        discovered = job.date_discovered.isoformat(timespec="minutes")
        print(f"[{job.id}] {job.title}")
        print(f"    {job.company} | {location}")
        print(f"    Discovered: {discovered}")
        print(f"    {job.job_url}\n")


if __name__ == "__main__":
    main()
