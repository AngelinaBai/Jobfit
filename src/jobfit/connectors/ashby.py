from __future__ import annotations

import hashlib
import html
from datetime import datetime

import requests

from jobfit.connectors.base import NormalizedJob


class AshbyConnector:
    BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{board}"

    def __init__(self, timeout_seconds: float = 20.0, session: requests.Session | None = None):
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def fetch_jobs(self, *, source_identifier: str, company_name: str) -> list[NormalizedJob]:
        response = self.session.get(
            self.BASE_URL.format(board=source_identifier),
            params={"includeCompensation": "true"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ValueError("Ashby response must contain a jobs list")

        jobs: list[NormalizedJob] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            external_id = str(item.get("id") or item.get("jobUrl") or "").strip()
            title = str(item.get("title") or "").strip()
            job_url = str(item.get("jobUrl") or item.get("applyUrl") or "").strip()
            if not external_id or not title or not job_url:
                continue
            location = item.get("location") or item.get("secondaryLocations")
            if isinstance(location, list):
                location = ", ".join(str(x) for x in location)
            description = html.unescape(
                str(item.get("descriptionPlain") or item.get("descriptionHtml") or item.get("description") or "")
            )
            date_posted = None
            published = item.get("publishedAt")
            if isinstance(published, str):
                try:
                    date_posted = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except ValueError:
                    pass
            digest = hashlib.sha256(
                "|".join([title, str(location or ""), description, job_url]).encode("utf-8")
            ).hexdigest()
            jobs.append(
                NormalizedJob(
                    external_job_id=external_id,
                    title=title,
                    company=company_name,
                    location=str(location).strip() if location else None,
                    description=description,
                    job_url=job_url,
                    date_posted=date_posted,
                    content_hash=digest,
                )
            )
        return jobs
