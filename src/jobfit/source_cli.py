from __future__ import annotations

import argparse

from sqlalchemy import select

from jobfit.config import Settings
from jobfit.db import build_engine, build_session_factory
from jobfit.logging_config import configure_logging
from jobfit.models import JobSource
from jobfit.services.sources import add_source, seed_default_sources
from jobfit.services.career_discovery import discover_career_source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage JobFit company sources")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add or enable one Greenhouse board")
    add_parser.add_argument("--company", required=True)
    add_parser.add_argument("--token", required=True, help="Greenhouse board token")
    add_parser.add_argument("--url")

    discover_parser = subparsers.add_parser("discover", help="Analyze and add a public company career page")
    discover_parser.add_argument("--company", required=True)
    discover_parser.add_argument("--url", required=True)

    subparsers.add_parser("seed", help="Add the built-in starter source set")
    subparsers.add_parser("list", help="List configured sources")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        if args.command == "add":
            source, created = add_source(
                session,
                company_name=args.company,
                source_identifier=args.token,
                careers_url=args.url,
            )
            action = "Added" if created else "Updated existing"
            print(f"{action} source {source.id}: {source.company_name} ({source.source_identifier})")
            return


        if args.command == "discover":
            detection = discover_career_source(args.url, timeout_seconds=settings.http_timeout_seconds)
            source, created = add_source(
                session,
                company_name=args.company,
                source_type=detection.source_type,
                source_identifier=detection.source_identifier,
                careers_url=detection.careers_url,
            )
            action = "Added" if created else "Updated existing"
            print(f"{action} source {source.id}: {source.company_name} ({source.source_type})")
            print(detection.detail)
            return

        if args.command == "seed":
            added, existing = seed_default_sources(session)
            print(f"Starter sources ready: {added} added, {existing} already present.")
            return

        sources = session.scalars(select(JobSource).order_by(JobSource.id)).all()
        for source in sources:
            state = "enabled" if source.enabled else "disabled"
            print(f"{source.id}: {source.company_name} | {source.source_identifier} | {state}")


if __name__ == "__main__":
    main()
