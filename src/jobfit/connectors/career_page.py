from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from jobfit.connectors.base import NormalizedJob
from jobfit.connectors.browser_render import BrowserRenderError, render_public_page
from jobfit.connectors.public_listings import (
    extract_public_listing_jobs,
    supports_public_listing_host,
)


class CareerPageConnector:
    """Best-effort parser for public career sites.

    It prefers schema.org JobPosting JSON-LD, then follows likely job-detail links
    on the supplied career page. It intentionally does not bypass login walls,
    CAPTCHAs, or other access controls.
    """

    def __init__(self, timeout_seconds: float = 20.0, session: requests.Session | None = None):
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.headers = {"User-Agent": "JobFit/0.9.0 (+public-career-page-parser)"}

    def fetch_jobs(self, *, source_identifier: str, company_name: str) -> list[NormalizedJob]:
        root_url = source_identifier
        response = self.session.get(root_url, timeout=self.timeout_seconds, headers=self.headers)
        response.raise_for_status()
        root_html = response.text
        root_url = response.url or root_url

        if supports_public_listing_host(root_url):
            # These sites render real listing cards in JavaScript. Their static
            # shells may contain unrelated links that resemble job pages, so the
            # generic crawler must not run before the rendered-page pass.
            static_jobs = extract_public_listing_jobs(root_html, root_url, company_name)
            if static_jobs:
                return static_jobs
        else:
            jobs = self._extract_from_root(root_html, root_url, company_name, render_details=False)
            if jobs:
                return list(jobs.values())

        # JavaScript-heavy career sites often return an almost empty HTML shell to
        # requests. Render the public page in headless Chromium and retry.
        try:
            rendered_url, rendered_html = render_public_page(
                root_url, timeout_seconds=self.timeout_seconds
            )
        except BrowserRenderError as exc:
            raise RuntimeError(
                f"Static career-page scan found 0 jobs and browser rendering failed: {exc}"
            ) from exc

        jobs = self._extract_from_root(
            rendered_html, rendered_url, company_name, render_details=True
        )
        return list(jobs.values())

    def _extract_from_root(
        self,
        root_html: str,
        root_url: str,
        company_name: str,
        *,
        render_details: bool,
    ) -> dict[str, NormalizedJob]:
        jobs: dict[str, NormalizedJob] = {}
        for job in self._jsonld_jobs(root_html, root_url, company_name):
            jobs[job.external_job_id] = job
        for job in extract_public_listing_jobs(root_html, root_url, company_name):
            jobs[job.external_job_id] = job

        # Supported large public career sites expose complete, stable listing
        # cards after rendering. Avoid crawling unrelated navigation/detail links
        # once those cards have been recognized.
        if jobs:
            return jobs

        soup = BeautifulSoup(root_html, "html.parser")
        links = self._candidate_links(soup, root_url)
        rendered_detail_budget = 20
        for url in links[:120]:
            detail_html = ""
            detail_url = url
            try:
                detail = self.session.get(url, timeout=self.timeout_seconds, headers=self.headers)
                detail.raise_for_status()
                detail_html = detail.text
                detail_url = detail.url or url
            except requests.RequestException:
                detail_html = ""

            detail_jobs = self._jsonld_jobs(detail_html, detail_url, company_name) if detail_html else []
            for job in detail_jobs:
                jobs[job.external_job_id] = job
            if detail_jobs:
                continue

            fallback = self._fallback_detail(detail_html, detail_url, company_name) if detail_html else None
            if fallback:
                jobs[fallback.external_job_id] = fallback
                continue

            if render_details and rendered_detail_budget > 0:
                rendered_detail_budget -= 1
                try:
                    final_url, html = render_public_page(
                        url, timeout_seconds=self.timeout_seconds
                    )
                except BrowserRenderError:
                    continue
                rendered_jobs = self._jsonld_jobs(html, final_url, company_name)
                for job in rendered_jobs:
                    jobs[job.external_job_id] = job
                if not rendered_jobs:
                    rendered_fallback = self._fallback_detail(html, final_url, company_name)
                    if rendered_fallback:
                        jobs[rendered_fallback.external_job_id] = rendered_fallback

        return jobs

    @staticmethod
    def _candidate_links(soup: BeautifulSoup, base_url: str) -> list[str]:
        base_host = urlparse(base_url).netloc.lower()
        seen: set[str] = set()
        results: list[str] = []
        keywords = ("job", "jobs", "career", "careers", "position", "opening", "role")
        for tag in soup.find_all("a", href=True):
            href = str(tag.get("href") or "").strip()
            text = " ".join(tag.stripped_strings).lower()
            if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                continue
            url = urljoin(base_url, href)
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"}:
                continue
            haystack = f"{parsed.path.lower()} {text}"
            if not any(keyword in haystack for keyword in keywords):
                continue
            # Prefer same-host links, but allow known external ATS job-detail hosts.
            host = parsed.netloc.lower()
            if host != base_host and not any(x in host for x in ("greenhouse.io", "lever.co", "ashbyhq.com", "workdayjobs.com")):
                continue
            normalized = url.split("#", 1)[0]
            if normalized not in seen:
                seen.add(normalized)
                results.append(normalized)
        return results

    @classmethod
    def _jsonld_jobs(cls, html: str, page_url: str, company_name: str) -> list[NormalizedJob]:
        soup = BeautifulSoup(html, "html.parser")
        jobs: list[NormalizedJob] = []
        for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
            raw = script.string or script.get_text() or ""
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            for item in cls._walk_jsonld(payload):
                if str(item.get("@type") or "").lower() != "jobposting":
                    continue
                title = cls._text(item.get("title"))
                if not title:
                    continue
                url = cls._text(item.get("url")) or page_url
                description = BeautifulSoup(cls._text(item.get("description")), "html.parser").get_text(" ", strip=True)
                location = cls._extract_location(item)
                date_posted = cls._parse_date(item.get("datePosted"))
                identifier = item.get("identifier")
                if isinstance(identifier, dict):
                    external_id = cls._text(identifier.get("value"))
                else:
                    external_id = cls._text(identifier)
                external_id = external_id or hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
                digest = hashlib.sha256("|".join([title, location or "", description, url]).encode("utf-8")).hexdigest()
                jobs.append(NormalizedJob(external_id, title, company_name, location, description, url, date_posted, digest))
        return jobs

    @staticmethod
    def _walk_jsonld(payload):
        if isinstance(payload, dict):
            yield payload
            graph = payload.get("@graph")
            if isinstance(graph, list):
                for item in graph:
                    yield from CareerPageConnector._walk_jsonld(item)
        elif isinstance(payload, list):
            for item in payload:
                yield from CareerPageConnector._walk_jsonld(item)

    @staticmethod
    def _text(value) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @classmethod
    def _extract_location(cls, item: dict) -> str | None:
        locations = item.get("jobLocation")
        if not locations:
            if item.get("jobLocationType") == "TELECOMMUTE":
                return "Remote"
            return None
        if not isinstance(locations, list):
            locations = [locations]
        parts: list[str] = []
        for loc in locations:
            if not isinstance(loc, dict):
                continue
            address = loc.get("address") or {}
            if not isinstance(address, dict):
                continue
            bits = [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")]
            text = ", ".join(str(x).strip() for x in bits if x)
            if text:
                parts.append(text)
        return " | ".join(parts) or None

    @staticmethod
    def _parse_date(value) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @classmethod
    def _fallback_detail(cls, html: str, page_url: str, company_name: str) -> NormalizedJob | None:
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        title = " ".join(h1.stripped_strings).strip() if h1 else ""
        if not title or len(title) > 220:
            return None
        main = soup.find("main") or soup.body
        description = " ".join(main.stripped_strings) if main else ""
        if len(description) < 120:
            return None
        # Avoid treating generic careers/index pages as individual postings.
        text = description.lower()
        if not any(term in text for term in ("responsibilities", "qualifications", "requirements", "what you'll", "what you will", "experience")):
            return None
        location = None
        for selector in ("[class*='location']", "[data-location]", "[itemprop='jobLocation']"):
            node = soup.select_one(selector)
            if node:
                location = " ".join(node.stripped_strings).strip() or None
                break
        external_id = hashlib.sha256(page_url.encode("utf-8")).hexdigest()[:32]
        digest = hashlib.sha256("|".join([title, location or "", description, page_url]).encode("utf-8")).hexdigest()
        return NormalizedJob(external_id, title, company_name, location, description, page_url, None, digest)
