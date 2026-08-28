from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote, urlsplit

from jobfit.models import Job


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[\w]+", normalized))


def _canonical_job_url(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    host = parsed.hostname.casefold()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+", "/", unquote(parsed.path)).rstrip("/").casefold()
    if not path:
        return ""
    return f"{host}{path}"


def job_duplicate_keys(job: Job) -> set[str]:
    """Return conservative identities used to suppress rediscovered tracked jobs.

    Source/external IDs remain the persistence identity. These keys are only a
    presentation-layer safeguard, so no job or application history is deleted.
    """
    keys: set[str] = set()
    canonical_url = _canonical_job_url(job.job_url)
    if canonical_url:
        keys.add(f"url:{canonical_url}")

    company = _normalize_text(job.company)
    title = _normalize_text(job.title)
    location = _normalize_text(job.location)
    if company and title:
        keys.add(f"role:{company}|{title}|{location}")
    return keys
