from __future__ import annotations

from dataclasses import dataclass

from jobfit.connectors.base import JobConnector, NormalizedJob
from jobfit.models import JobSource
from jobfit.services.career_discovery import CareerSourceDetection
from jobfit.services.scan_verification import verify_scan_jobs


class SourceVerificationInconclusive(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VerifiedSourceCandidate:
    detection: CareerSourceDetection
    jobs: tuple[NormalizedJob, ...]


def verify_source_candidate(
    *,
    company_name: str,
    detection: CareerSourceDetection,
    connector: JobConnector,
) -> VerifiedSourceCandidate:
    """Extract and validate jobs before a monitored source is persisted."""
    candidate = JobSource(
        company_name=company_name.strip(),
        source_type=detection.source_type,
        source_identifier=detection.source_identifier,
        careers_url=detection.careers_url,
        enabled=True,
    )
    extracted = connector.fetch_jobs(
        source_identifier=detection.source_identifier,
        company_name=company_name.strip(),
    )
    verified = verify_scan_jobs(candidate, extracted)
    if not verified:
        raise SourceVerificationInconclusive(
            "No individual job listings could be verified. The board may truly be empty, "
            "or its page format may not be supported yet; the source was not added."
        )
    return VerifiedSourceCandidate(detection=detection, jobs=tuple(verified))
