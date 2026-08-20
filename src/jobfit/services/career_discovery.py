from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from jobfit.connectors.browser_render import BrowserRenderError, render_public_page


@dataclass(frozen=True, slots=True)
class CareerSourceDetection:
    source_type: str
    source_identifier: str
    careers_url: str
    detail: str


class CareerDiscoveryError(RuntimeError):
    pass


_GREENHOUSE_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
_LEVER_HOSTS = {"jobs.lever.co"}
_ASHBY_HOSTS = {"jobs.ashbyhq.com"}


def _clean_host(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host.removeprefix("www.")


def _from_url(url: str) -> CareerSourceDetection | None:
    parsed = urlparse(url)
    host = _clean_host(url)
    parts = [part for part in parsed.path.split("/") if part]

    if host in _GREENHOUSE_HOSTS and parts:
        if parts[0].lower() == "embed":
            token_match = re.search(r"(?:^|&)for=([A-Za-z0-9_-]+)(?:&|$)", parsed.query, re.I)
            if token_match:
                return CareerSourceDetection(
                    "greenhouse",
                    token_match.group(1).lower(),
                    url,
                    "Detected embedded Greenhouse board from URL",
                )
            return None
        if parts[0].lower() in {"v1", "boards", "jobs", "job_board"}:
            return None
        return CareerSourceDetection("greenhouse", parts[0].lower(), url, "Detected Greenhouse from URL")
    if host in _LEVER_HOSTS and parts:
        return CareerSourceDetection("lever", parts[0].lower(), url, "Detected Lever from URL")
    if host in _ASHBY_HOSTS and parts:
        return CareerSourceDetection("ashby", parts[0], url, "Detected Ashby from URL")
    if "myworkdayjobs.com" in host or "workdayjobs.com" in host:
        return CareerSourceDetection("career_page", url, url, "Detected Workday career site; using public-page parser")
    if "smartrecruiters.com" in host:
        return CareerSourceDetection("career_page", url, url, "Detected SmartRecruiters career site; using public-page parser")
    return None


def _from_html(base_url: str, html: str) -> CareerSourceDetection | None:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    for tag in soup.find_all("a", href=True):
        href = str(tag.get("href") or "").strip()
        if href:
            candidates.append(href)
    candidates.extend(re.findall(r"https?://[^\"'<>\s]+", html))

    for candidate in candidates:
        direct = _from_url(candidate)
        if direct:
            return CareerSourceDetection(
                direct.source_type,
                direct.source_identifier,
                base_url,
                f"Detected {direct.source_type.title()} link on career page",
            )

    # Embedded Greenhouse board references sometimes do not use a visible board URL.
    for pattern in (
        r"greenhouse\.io/embed/job_board\?for=([A-Za-z0-9_-]+)",
        r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)",
        r"(?:boards|job-boards)\.greenhouse\.io/([A-Za-z0-9_-]+)",
    ):
        match = re.search(pattern, html, re.I)
        if match and match.group(1).lower() not in {"embed", "v1", "boards", "jobs", "job_board"}:
            return CareerSourceDetection("greenhouse", match.group(1).lower(), base_url, "Detected embedded Greenhouse board")

    return None


def discover_career_source(
    careers_url: str,
    *,
    timeout_seconds: float = 15.0,
    session: requests.Session | None = None,
) -> CareerSourceDetection:
    url = careers_url.strip()
    if not url.startswith(("http://", "https://")):
        raise CareerDiscoveryError("Career page URL must start with http:// or https://")

    direct = _from_url(url)
    if direct:
        return direct

    client = session or requests.Session()
    try:
        response = client.get(
            url,
            timeout=timeout_seconds,
            headers={"User-Agent": "JobFit/0.9.0 (+public-career-page-discovery)"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CareerDiscoveryError(f"Could not inspect career page: {exc}") from exc

    detected = _from_html(response.url or url, response.text)
    if detected:
        return detected

    # Some public career pages render their ATS links only after JavaScript runs.
    # Try a headless-browser render before falling back to the generic parser.
    canonical = (response.url or url).strip()
    try:
        rendered_url, rendered_html = render_public_page(
            canonical, timeout_seconds=timeout_seconds
        )
        rendered_detection = _from_html(rendered_url, rendered_html)
        if rendered_detection:
            return CareerSourceDetection(
                rendered_detection.source_type,
                rendered_detection.source_identifier,
                canonical,
                f"{rendered_detection.detail} after JavaScript rendering",
            )
        canonical = rendered_url or canonical
    except BrowserRenderError:
        # Discovery can still proceed with the generic connector; it will report
        # a more actionable error if rendering is required during the scan.
        pass

    # Keep the public career page itself as a source. The generic connector will
    # look for JobPosting JSON-LD and public job-detail links during each scan.
    return CareerSourceDetection(
        "career_page",
        canonical,
        canonical,
        "No supported ATS detected; using generic public career-page parser",
    )
