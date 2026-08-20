from __future__ import annotations

import hashlib
import html
from datetime import datetime

import requests

from jobfit.connectors.base import NormalizedJob


class LeverConnector:
    BASE_URL = "https://api.lever.co/v0/postings/{site}"

    def __init__(self, timeout_seconds: float = 20.0, session: requests.Session | None = None):
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def fetch_jobs(self, *, source_identifier: str, company_name: str) -> list[NormalizedJob]:
        response = self.session.get(
            self.BASE_URL.format(site=source_identifier),
            params={"mode": "json"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Lever response must be a list")

        jobs: list[NormalizedJob] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            external_id = str(item.get("id") or "").strip()
            title = str(item.get("text") or "").strip()
            job_url = str(item.get("hostedUrl") or item.get("applyUrl") or "").strip()
            if not external_id or not title or not job_url:
                continue

            categories = item.get("categories") or {}
            location = categories.get("location") if isinstance(categories, dict) else None
            description_parts = [
                str(item.get("descriptionPlain") or item.get("description") or ""),
                str(item.get("additionalPlain") or item.get("additional") or ""),
            ]
            for section in item.get("lists") or []:
                if isinstance(section, dict):
                    description_parts.append(str(section.get("text") or ""))
                    description_parts.append(str(section.get("content") or ""))
            description = html.unescape("\n".join(part for part in description_parts if part).strip())
            created = item.get("createdAt")
            date_posted = None
            if isinstance(created, (int, float)):
                date_posted = datetime.fromtimestamp(created / 1000).astimezone()
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
