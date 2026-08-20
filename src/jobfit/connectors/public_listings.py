from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from jobfit.connectors.base import NormalizedJob


_HOST_PATH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("janestreet.com", re.compile(r"/join-jane-street/position/(\d+)/?")),
    ("hudsonrivertrading.com", re.compile(r"/hrt-job/([^/?#]+)/?")),
    ("google.com", re.compile(r"/about/careers/applications/jobs/results/(\d+)-[^/?#]+")),
    ("metacareers.com", re.compile(r"/profile/job_details/(\d+)")),
    ("riotgames.com", re.compile(r"/[a-z]{2}/j/(\d+)/?")),
)


def _clean(value: str) -> str:
    return " ".join(value.split())


def _host_pattern(host: str) -> re.Pattern[str] | None:
    normalized = host.lower().removeprefix("www.")
    for suffix, pattern in _HOST_PATH_PATTERNS:
        if normalized == suffix or normalized.endswith(f".{suffix}"):
            return pattern
    return None


def supports_public_listing_host(url: str) -> bool:
    return _host_pattern(urlparse(url).netloc) is not None


def _card_for(anchor: Tag, host: str) -> Tag:
    if host.endswith("hudsonrivertrading.com"):
        card = anchor.find_parent(class_="hrt-card-item")
        if isinstance(card, Tag):
            return card
    if host.endswith("google.com"):
        node: Tag = anchor
        for _ in range(5):
            if node.find(re.compile(r"h[1-4]")) and len(_clean(node.get_text(" ", strip=True))) >= 40:
                return node
            parent = node.parent
            if not isinstance(parent, Tag):
                break
            node = parent
    return anchor


def _title(card: Tag, anchor: Tag, host: str) -> str:
    if host.endswith("hudsonrivertrading.com"):
        title_link = card.select_one("a.hrt-card-title")
        if title_link:
            return _clean(title_link.get_text(" ", strip=True))
    heading = card.find(re.compile(r"h[1-4]"))
    if heading:
        return _clean(heading.get_text(" ", strip=True))

    if host.endswith("riotgames.com"):
        primary = anchor.select_one(".job-row__col--primary")
        if primary:
            return _clean(primary.get_text(" ", strip=True))

    lines = [_clean(line) for line in anchor.get_text("\n", strip=True).splitlines()]
    lines = [line for line in lines if line]
    title = lines[0] if lines else ""
    if host.endswith("janestreet.com") and len(lines) >= 2:
        employment_type = lines[1].removeprefix("Full-Time: ").strip()
        if employment_type in {"New Grad", "Internship"}:
            title = f"{title} — {employment_type}"
    return title


def _location(card: Tag, anchor: Tag, host: str) -> str | None:
    if host.endswith("hudsonrivertrading.com"):
        list_node = card.select_one(".hrt-card-meta-desktop .hrt-card-info-list")
        if list_node:
            locations = [_clean(node.get_text(" ", strip=True)) for node in list_node.find_all("li")]
            return " | ".join(item for item in locations if item) or None

    if host.endswith("janestreet.com"):
        lines = [_clean(line) for line in anchor.get_text("\n", strip=True).splitlines() if _clean(line)]
        return lines[2] if len(lines) >= 3 else None

    if host.endswith("google.com"):
        locations = [_clean(node.get_text(" ", strip=True)) for node in card.select(".r0wTof")]
        return " | ".join(dict.fromkeys(item for item in locations if item)) or None

    if host.endswith("riotgames.com"):
        columns = anchor.select(".job-row__col--secondary")
        if columns:
            return _clean(columns[-1].get_text(" ", strip=True)) or None

    if host.endswith("metacareers.com"):
        text = _clean(anchor.get_text(" ", strip=True))
        heading = anchor.find(re.compile(r"h[1-4]"))
        title = _clean(heading.get_text(" ", strip=True)) if heading else ""
        remainder = text.removeprefix(title).strip()
        first = re.split(r"\s+[⋅|]\s+", remainder, maxsplit=1)[0]
        return first or None

    return None


def extract_public_listing_jobs(
    html: str,
    page_url: str,
    company_name: str,
) -> list[NormalizedJob]:
    """Extract job cards from supported rendered public career listings.

    These rules intentionally use stable host/path shapes and semantic card
    content rather than generated CSS class names wherever possible.
    """
    host = urlparse(page_url).netloc.lower().removeprefix("www.")
    pattern = _host_pattern(host)
    if pattern is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    jobs: dict[str, NormalizedJob] = {}
    for anchor in soup.find_all("a", href=True):
        raw_href = str(anchor.get("href") or "").strip()
        # Google currently emits card links relative to the applications root
        # ("jobs/results/<id>-<slug>"), even though the listing URL itself ends
        # in /jobs/results/. Resolve that shape explicitly to avoid duplicating
        # the jobs/results path.
        if host.endswith("google.com") and raw_href.startswith("jobs/results/"):
            href = urljoin(page_url, f"/about/careers/applications/{raw_href}")
        else:
            href = urljoin(page_url, raw_href)
        parsed = urlparse(href)
        match = pattern.search(parsed.path)
        if not match:
            continue
        if "not currently accepting applications" in anchor.get_text(" ", strip=True).lower():
            continue

        card = _card_for(anchor, host)
        title = _title(card, anchor, host)
        if not title or len(title) > 500 or title.lower() in {"apply now", "↳ apply now"}:
            continue
        location = _location(card, anchor, host)
        description = _clean(card.get_text(" ", strip=True))
        if description == title:
            description = "Public career listing."
        external_id = match.group(1)
        canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
        digest = hashlib.sha256(
            "|".join([title, location or "", description, canonical_url]).encode("utf-8")
        ).hexdigest()
        jobs[external_id] = NormalizedJob(
            external_job_id=external_id,
            title=title,
            company=company_name,
            location=location,
            description=description,
            job_url=canonical_url,
            date_posted=None,
            content_hash=digest,
        )
    return list(jobs.values())
