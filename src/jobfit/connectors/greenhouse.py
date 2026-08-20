from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from html import unescape
from typing import Any

import requests

from jobfit.connectors.base import NormalizedJob

logger = logging.getLogger(__name__)


class ConnectorError(RuntimeError):
    """Raised when a remote job source cannot be fetched or parsed."""


class GreenhouseConnector:
    BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"

    def __init__(self, *, timeout_seconds: float = 15.0, session: requests.Session | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def fetch_jobs(self, *, source_identifier: str, company_name: str) -> list[NormalizedJob]:
        url = self.BASE_URL.format(board_token=source_identifier)
        logger.info("greenhouse_fetch_started", extra={"board_token": source_identifier})

        try:
            response = self.session.get(
                url,
                params={"content": "true"},
                timeout=self.timeout_seconds,
                headers={"Accept": "application/json", "User-Agent": "JobFit/0.1"},
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise ConnectorError(f"Greenhouse request timed out for {source_identifier}") from exc
        except requests.RequestException as exc:
            raise ConnectorError(f"Greenhouse request failed for {source_identifier}: {exc}") from exc
        except ValueError as exc:
            raise ConnectorError(f"Greenhouse returned invalid JSON for {source_identifier}") from exc

        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise ConnectorError("Greenhouse response is missing a jobs list")

        normalized = [self._normalize_job(job, company_name) for job in jobs]
        logger.info(
            "greenhouse_fetch_completed",
            extra={"board_token": source_identifier, "jobs_found": len(normalized)},
        )
        return normalized

    @classmethod
    def _normalize_job(cls, raw: dict[str, Any], company_name: str) -> NormalizedJob:
        try:
            external_id = str(raw["id"])
            title = str(raw["title"]).strip()
            job_url = str(raw["absolute_url"]).strip()
        except KeyError as exc:
            raise ConnectorError(f"Greenhouse job is missing required field: {exc.args[0]}") from exc

        location_data = raw.get("location") or {}
        location = location_data.get("name") if isinstance(location_data, dict) else None
        description = unescape(str(raw.get("content") or "")).strip()
        date_posted = cls._parse_datetime(raw.get("updated_at"))
        content_hash = cls._content_hash(title, location, description, job_url)

        return NormalizedJob(
            external_job_id=external_id,
            title=title,
            company=company_name,
            location=location,
            description=description,
            job_url=job_url,
            date_posted=date_posted,
            content_hash=content_hash,
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            logger.warning("greenhouse_invalid_datetime", extra={"value": value})
            return None

    @staticmethod
    def _content_hash(title: str, location: str | None, description: str, job_url: str) -> str:
        canonical = "|".join([title, location or "", description, job_url])
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
