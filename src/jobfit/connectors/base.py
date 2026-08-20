from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class NormalizedJob:
    external_job_id: str
    title: str
    company: str
    location: str | None
    description: str
    job_url: str
    date_posted: datetime | None
    content_hash: str


class JobConnector(Protocol):
    def fetch_jobs(self, *, source_identifier: str, company_name: str) -> list[NormalizedJob]: ...
