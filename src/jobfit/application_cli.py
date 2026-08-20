from __future__ import annotations

import argparse
import webbrowser

from jobfit.config import Settings
from jobfit.db import build_engine, build_session_factory
from jobfit.logging_config import configure_logging
from jobfit.models import ApplicationStatus, Base
from jobfit.services.applications import get_job, list_applications, set_application_status

STATUSES = tuple(status.value for status in ApplicationStatus)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open and track JobFit applications")
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser("open", help="Open a posting in your browser")
    open_parser.add_argument("job_id", type=int)

    mark_parser = subparsers.add_parser("mark", help="Save or update an application status")
    mark_parser.add_argument("job_id", type=int)
    mark_parser.add_argument("status", choices=STATUSES)
    mark_parser.add_argument("--resume", dest="resume_version")
    mark_parser.add_argument("--notes")
    mark_parser.add_argument(
        "--open",
        action="store_true",
        help="Open the posting after recording the status",
    )

    list_parser = subparsers.add_parser("list", help="List tracked applications")
    list_parser.add_argument("--status", choices=STATUSES)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        if args.command == "open":
            job = get_job(session, args.job_id)
            print(f"Opening: {job.title} — {job.company}")
            webbrowser.open(job.job_url)
            return

        if args.command == "mark":
            application = set_application_status(
                session,
                job_id=args.job_id,
                status=args.status,
                notes=args.notes,
                resume_version=args.resume_version,
            )
            job = application.job
            print(f"Recorded [{application.status}] for job {job.id}: {job.title} — {job.company}")
            if application.applied_at:
                print(f"Applied at: {application.applied_at.isoformat(timespec='minutes')}")
            if application.resume_version:
                print(f"Resume: {application.resume_version}")
            if application.notes:
                print(f"Notes: {application.notes}")
            if args.open:
                webbrowser.open(job.job_url)
            return

        applications = list_applications(session, status=args.status)
        if not applications:
            print("No tracked applications found.")
            return
        print(f"Tracked applications: {len(applications)}\n")
        for application in applications:
            job = application.job
            location = job.location or "Location not listed"
            applied = (
                application.applied_at.isoformat(timespec="minutes")
                if application.applied_at
                else "—"
            )
            print(f"[{job.id}] {job.title}")
            print(f"    {job.company} | {location}")
            print(f"    Status: {application.status} | Applied: {applied}")
            if application.resume_version:
                print(f"    Resume: {application.resume_version}")
            if application.notes:
                print(f"    Notes: {application.notes}")
            print(f"    {job.job_url}\n")


if __name__ == "__main__":
    main()
