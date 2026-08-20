from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, or_, select

from jobfit.models import Job, JobStatus


DEFAULT_TITLE_KEYWORDS = (
    "quant",
    "data",
    "analytics",
    "risk",
    "research",
    "machine learning",
    "financial",
    "finance",
    "trading",
)

SENIOR_MARKERS = (
    "senior",
    "sr.",
    "sr ",
    "staff",
    "principal",
    "director",
    "manager",
    "lead",
    "head of",
    "vice president",
    "vp ",
)

TITLE_SENIORITY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "intern",
        (
            r"\bintern(?:ship)?\b",
            r"\bco[- ]?op\b",
        ),
    ),
    (
        "new-grad",
        (
            r"\bnew grad(?:uate)?\b",
            r"\brecent grad(?:uate)?\b",
            r"\bgraduate program\b",
            r"\buniversity graduate\b",
            r"\bcampus hire\b",
            r"\b20\d{2} grads?\b",
        ),
    ),
    (
        "entry",
        (
            r"\bentry[- ]level\b",
            r"\bearly career\b",
            r"\bjunior\b",
            r"\bengineer i\b",
            r"\bscientist i\b",
            r"\banalyst i\b",
            r"\blevel i\b",
        ),
    ),
    (
        "entry-adjacent",
        (
            r"\bassociate\b",
            r"\banalyst\b",
        ),
    ),
)

MID_MARKERS = ("ii", "level 2", "mid-level", "mid level")


def classify_title_seniority(title: str) -> str:
    """Classify seniority using only explicit title wording.

    This is intentionally conservative: unknown means the title itself does not
    make the level clear. Full-description requirements are handled separately.
    """
    title_text = " ".join(title.lower().split())
    if any(marker in title_text for marker in SENIOR_MARKERS):
        return "senior"
    for label, patterns in TITLE_SENIORITY_PATTERNS:
        if any(re.search(pattern, title_text) for pattern in patterns):
            return label
    if any(re.search(rf"\b{re.escape(marker)}\b", title_text) for marker in MID_MARKERS):
        return "mid"
    return "unknown"


def title_seniority_priority(label: str) -> int:
    """Higher values should appear earlier in entry-level recommendations."""
    return {
        "intern": 5,
        "new-grad": 5,
        "entry": 4,
        "entry-adjacent": 3,
        "unknown": 2,
        "mid": 1,
        "senior": 0,
    }.get(label, 0)


@dataclass(frozen=True, slots=True)
class JobFilter:
    title_keywords: tuple[str, ...] = DEFAULT_TITLE_KEYWORDS
    location_keywords: tuple[str, ...] = ()
    seniority: str = "entry"
    since_hours: int | None = None
    limit: int = 100


def split_keywords(raw: str | None, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())




def matches_terms(text: str, terms: list[str] | tuple[str, ...]) -> bool:
    """Match at least one term without matching inside unrelated words."""
    if not terms:
        return True
    normalized = " ".join(text.lower().split())
    for term in terms:
        escaped = re.escape(term.strip().lower())
        if re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", normalized):
            return True
    return False

def classify_seniority(title: str, description: str = "") -> str:
    title_signal = classify_title_seniority(title)
    required_years = extract_required_experience_years(description)

    # Explicit experience requirements override optimistic title language.
    if required_years is not None:
        if required_years >= 5:
            return "senior"
        if required_years >= 2:
            return "mid"

    if title_signal in {"intern", "new-grad"}:
        return "intern" if title_signal == "intern" else "entry"
    if title_signal in {"entry", "entry-adjacent"}:
        return "entry"
    if title_signal in {"senior", "mid"}:
        return title_signal
    if required_years is not None and required_years <= 1:
        return "entry"
    return "unknown"


def extract_required_experience_years(description: str) -> int | None:
    """Extract the minimum explicitly required years of experience.

    Returns the strongest stated minimum. Quantified experience in preferred
    qualifications is included because JobFit's early-career eligibility rule
    treats it as a meaningful experience floor even when it is not mandatory.
    """
    text = " ".join(description.lower().split())
    candidates: list[int] = []

    patterns = (
        r"(?:minimum(?: of)?|at least|requires?|required)\s+(\d{1,2})\+?\s*(?:years?|yrs?)",
        r"(\d{1,2})\+\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|professional\s+|work\s+)?experience",
        r"(\d{1,2})\s*(?:-|–|to)\s*\d{1,2}\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|professional\s+|work\s+)?experience",
        r"(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|professional\s+|work\s+)?experience\s+(?:is\s+)?required",
        r"(?:experience|background)\s*:\s*(\d{1,2})\+?\s*(?:years?|yrs?)",
    )

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidates.append(int(match.group(1)))

    return max(candidates) if candidates else None


def matches_seniority(job: Job, requested: str) -> bool:
    if requested == "all":
        return True
    classified = classify_seniority(job.title, job.description)
    if requested == "entry":
        # Unknown titles are retained unless they contain an explicit senior marker.
        return classified in {"intern", "entry", "unknown"}
    return classified == requested


def build_job_query(filters: JobFilter, *, now: datetime | None = None) -> Select[tuple[Job]]:
    query = select(Job).where(Job.status == JobStatus.ACTIVE.value)

    if filters.title_keywords:
        title_conditions = [Job.title.ilike(f"%{keyword}%") for keyword in filters.title_keywords]
        query = query.where(or_(*title_conditions))

    if filters.location_keywords:
        location_conditions = [
            Job.location.ilike(f"%{keyword}%") for keyword in filters.location_keywords
        ]
        query = query.where(or_(*location_conditions))

    if filters.since_hours is not None:
        observed_now = now or datetime.now(UTC)
        query = query.where(Job.date_discovered >= observed_now - timedelta(hours=filters.since_hours))

    return query.order_by(Job.date_discovered.desc(), Job.date_posted.desc()).limit(filters.limit)


def matches_job(job: Job, filters: JobFilter) -> bool:
    title = job.title.lower()
    location = (job.location or "").lower()
    if filters.title_keywords and not any(keyword.lower() in title for keyword in filters.title_keywords):
        return False
    if filters.location_keywords and not any(
        keyword.lower() in location for keyword in filters.location_keywords
    ):
        return False
    return matches_seniority(job, filters.seniority)


def filter_jobs_in_memory(jobs: list[Job], filters: JobFilter) -> list[Job]:
    return [job for job in jobs if matches_job(job, filters)]
