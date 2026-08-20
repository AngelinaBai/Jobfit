from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from jobfit.models import Job
from jobfit.profile import ANGELINA_PROFILE, CandidateProfile
from jobfit.services.filtering import (
    classify_seniority,
    classify_title_seniority,
    extract_required_experience_years,
    title_seniority_priority,
)


class SponsorshipAssessment(StrEnum):
    LIKELY_COMPATIBLE = "likely-compatible"
    LIKELY_NOT_COMPATIBLE = "likely-not-compatible"
    UNKNOWN = "unknown"


class DegreeAssessment(StrEnum):
    PHD_REQUIRED = "phd-required"
    PHD_PREFERRED = "phd-preferred"
    PHD_ACCEPTABLE = "phd-acceptable"
    NONE = "none"


class CareerTrack(StrEnum):
    QUANT = "quant"
    TECH = "tech"
    ADJACENT = "adjacent"


NEGATIVE_SPONSORSHIP_PATTERNS = (
    r"(?:will|does|do) not (?:provide|offer|sponsor)",
    r"no (?:visa|immigration) sponsorship",
    r"without (?:current or future )?sponsorship",
    r"not eligible for (?:visa|immigration) sponsorship",
    r"must be (?:a )?u\.s\. citizen",
    r"u\.s\. citizenship (?:is )?required",
    r"must be authorized to work.*without sponsorship",
    r"unable to sponsor",
    r"cannot sponsor",
    r"no cpt",
    r"no opt",
)

POSITIVE_SPONSORSHIP_PATTERNS = (
    r"visa sponsorship (?:is )?(?:available|provided|offered)",
    r"will sponsor",
    r"sponsorship available",
    r"open to (?:f-?1|opt|cpt)",
    r"f-?1 (?:students|candidates)",
    r"stem opt",
    r"opt (?:candidates|students|eligible)",
    r"cpt (?:candidates|students|eligible)",
    r"h-?1b sponsorship",
)

US_LOCATION_MARKERS = (
    "united states", "usa", "u.s.", "remote - us", "remote, us",
    "new york", "san francisco", "california", "los angeles", "seattle",
    "washington", "boston", "massachusetts", "chicago", "illinois",
    "austin", "texas", "denver", "colorado", "atlanta", "georgia",
    "miami", "florida", "pennsylvania", "new jersey", "connecticut",
    "virginia", "maryland", "north carolina",
)
CHINA_LOCATION_MARKERS = (
    "china", "beijing", "shanghai", "shenzhen", "guangzhou", "hangzhou",
    "chengdu", "nanjing", "wuhan", "suzhou", "xiamen", "tianjin",
)
SINGAPORE_LOCATION_MARKERS = ("singapore",)
OTHER_LOCATION_MARKERS = (
    "london", "paris", "berlin", "tokyo", "india", "canada", "toronto",
    "vancouver", "dublin", "amsterdam", "australia", "sydney", "hong kong",
    "zurich", "switzerland", "dubai", "uae",
)

PREFERRED_REGIONS = ("us", "china", "singapore")


@dataclass(frozen=True, slots=True)
class MatchResult:
    score: int
    seniority: str
    title_seniority: str
    title_seniority_priority: int
    us_location: bool | None
    location_region: str
    preferred_location: bool
    sponsorship: SponsorshipAssessment
    degree: DegreeAssessment
    matched_skills: tuple[str, ...]
    matched_domains: tuple[str, ...]
    reasons: tuple[str, ...]
    concerns: tuple[str, ...]
    exclusion_reasons: tuple[str, ...]
    required_experience_years: int | None
    entry_level_eligible: bool
    eligible: bool
    career_track: CareerTrack


def classify_career_track(title: str, description: str = "") -> CareerTrack:
    title_text = " ".join(title.lower().split())
    full_text = f"{title_text} {' '.join(description.lower().split())}"
    quant_markers = (
        "quant", "trading", "trader", "algorithm developer", "systematic",
        "portfolio", "market risk", "financial engineering", "research analyst",
    )
    tech_markers = (
        "software", "data", "machine learning", "ml ", "ai ", "artificial intelligence",
        "research scientist", "engineer", "developer", "analytics", "applied scientist",
    )
    if any(marker in title_text for marker in quant_markers):
        return CareerTrack.QUANT
    if any(marker in title_text for marker in tech_markers):
        return CareerTrack.TECH
    if any(marker in full_text for marker in quant_markers):
        return CareerTrack.QUANT
    if any(marker in full_text for marker in tech_markers):
        return CareerTrack.TECH
    return CareerTrack.ADJACENT


def _contains(text: str, term: str) -> bool:
    if len(term.strip()) <= 2:
        return re.search(rf"\b{re.escape(term.strip())}\b", text) is not None
    return term.lower() in text


def assess_sponsorship(description: str) -> SponsorshipAssessment:
    text = " ".join(description.lower().split())
    if any(re.search(pattern, text) for pattern in NEGATIVE_SPONSORSHIP_PATTERNS):
        return SponsorshipAssessment.LIKELY_NOT_COMPATIBLE
    if any(re.search(pattern, text) for pattern in POSITIVE_SPONSORSHIP_PATTERNS):
        return SponsorshipAssessment.LIKELY_COMPATIBLE
    return SponsorshipAssessment.UNKNOWN


def classify_location(location: str | None) -> str:
    if not location:
        return "unknown"
    text = " ".join(location.lower().split())
    if any(marker in text for marker in US_LOCATION_MARKERS):
        return "us"
    if any(marker in text for marker in CHINA_LOCATION_MARKERS):
        return "china"
    if any(marker in text for marker in SINGAPORE_LOCATION_MARKERS):
        return "singapore"
    if any(marker in text for marker in OTHER_LOCATION_MARKERS):
        return "other"
    return "unknown"


def assess_us_location(location: str | None) -> bool | None:
    region = classify_location(location)
    if region == "us":
        return True
    if region in {"china", "singapore", "other"}:
        return False
    return None


def assess_degree_requirement(title: str, description: str) -> DegreeAssessment:
    """Classify PhD language conservatively.

    PhD-only roles are excluded. Phrases that explicitly allow bachelor's or
    master's degrees remain eligible, and 'preferred' does not become a hard
    exclusion.
    """
    title_text = " ".join(title.lower().split())
    text = " ".join(description.lower().split())
    phd = r"(?:ph\.?d\.?|doctorate|doctoral degree)"

    if re.search(phd, title_text):
        return DegreeAssessment.PHD_REQUIRED

    # Explicit alternative degree paths mean a PhD is acceptable, not required.
    alternative_patterns = (
        rf"(?:bachelor'?s|master'?s|bs|ba|ms|ma|mfe|mba)[^.;:]{{0,50}}(?:or|/)[^.;:]{{0,25}}{phd}",
        rf"{phd}[^.;:]{{0,35}}(?:or|/)[^.;:]{{0,35}}(?:bachelor'?s|master'?s|bs|ba|ms|ma|mfe|mba)",
        rf"(?:bs|ms|ph\.?d\.?)\s*(?:/|,)",
    )
    if any(re.search(pattern, text) for pattern in alternative_patterns):
        return DegreeAssessment.PHD_ACCEPTABLE

    preferred_patterns = (
        rf"{phd}[^.;:]{{0,35}}(?:preferred|a plus|nice to have)",
        rf"(?:preferred|ideally)[^.;:]{{0,35}}{phd}",
    )
    if any(re.search(pattern, text) for pattern in preferred_patterns):
        return DegreeAssessment.PHD_PREFERRED

    required_patterns = (
        rf"(?:requires?|required|must have|minimum qualification(?:s)?(?: include)?)[^.;:]{{0,45}}{phd}",
        rf"{phd}[^.;:]{{0,35}}(?:is required|required|minimum)",
        rf"(?:education|degree|qualification(?:s)?)\s*:\s*{phd}",
        rf"{phd}\s+in\s+[a-z0-9 ,&/\-]+(?:required|or equivalent experience)",
    )
    if any(re.search(pattern, text) for pattern in required_patterns):
        return DegreeAssessment.PHD_REQUIRED

    return DegreeAssessment.NONE


def score_job(job: Job, profile: CandidateProfile = ANGELINA_PROFILE) -> MatchResult:
    title = job.title.lower()
    description = job.description.lower()
    full_text = f"{title} {description}"
    required_experience_years = extract_required_experience_years(job.description)
    title_seniority = classify_title_seniority(job.title)
    seniority = classify_seniority(job.title, job.description)
    degree = assess_degree_requirement(job.title, job.description)
    location_region = classify_location(job.location)
    preferred_location = location_region in PREFERRED_REGIONS
    sponsorship = assess_sponsorship(job.description)
    us_location = assess_us_location(job.location)

    exclusion_reasons: list[str] = []
    if degree == DegreeAssessment.PHD_REQUIRED:
        exclusion_reasons.append("PhD required")
    # Experience requirements affect ranking but are not hard exclusions. This
    # avoids hiding otherwise strong matches when a posting describes an ideal
    # candidate or uses an inflated experience target.
    if title_seniority == "senior":
        exclusion_reasons.append("senior-level role")
    elif title_seniority == "mid":
        exclusion_reasons.append("mid-level role")
    if location_region == "other":
        exclusion_reasons.append("outside preferred regions (U.S., China, Singapore)")
    # Work-authorization language is a hard conflict only for U.S. roles.
    if location_region == "us" and sponsorship == SponsorshipAssessment.LIKELY_NOT_COMPATIBLE:
        exclusion_reasons.append("U.S. posting indicates incompatible sponsorship/work authorization")

    entry_level_eligible = not any(
        reason in {"senior-level role", "mid-level role", "PhD required"}
        for reason in exclusion_reasons
    )
    eligible = not exclusion_reasons

    role_matches = tuple(term for term in profile.target_roles if term in title)
    skill_matches = tuple(term.strip() for term in profile.skills if _contains(full_text, term))
    domain_matches = tuple(term for term in profile.domain_terms if _contains(full_text, term))
    education_matches = tuple(term for term in profile.education_terms if _contains(full_text, term))

    score = 0
    reasons: list[str] = []
    concerns: list[str] = []

    if role_matches:
        score += min(35, 22 + 5 * (len(role_matches) - 1))
        reasons.append(f"target role match: {role_matches[0]}")
    elif any(term in title for term in ("data", "quant", "research", "analytics", "risk", "ai", "machine learning")):
        score += 18
        reasons.append("title is adjacent to your target functions")

    if skill_matches:
        score += min(30, 5 * len(skill_matches))
        reasons.append("skills match: " + ", ".join(skill_matches[:5]))

    if domain_matches:
        score += min(15, 3 * len(domain_matches))
        reasons.append("domain match: " + ", ".join(domain_matches[:4]))

    if education_matches:
        score += min(8, 2 * len(education_matches))

    if title_seniority in {"intern", "new-grad", "entry"}:
        score += 14
        reasons.append(f"title explicitly signals {title_seniority}")
    elif title_seniority == "entry-adjacent":
        score += 9
        reasons.append("title is commonly associated with early-career hiring")
    elif seniority == "entry":
        score += 6
        reasons.append("description supports entry-level eligibility")
    elif seniority == "unknown":
        score += 1
        concerns.append("title does not explicitly state an entry-level hiring track")

    if location_region == "us":
        score += 6
        reasons.append("U.S. location")
    elif location_region == "china":
        score += 3
        reasons.append("China location is within your preferred regions")
    elif location_region == "singapore":
        score += 3
        reasons.append("Singapore location is within your preferred regions")
    elif location_region == "unknown":
        concerns.append("location could not be classified confidently")
    else:
        score -= 15
        concerns.append("posting is outside your preferred regions")

    if location_region == "us":
        if sponsorship == SponsorshipAssessment.LIKELY_COMPATIBLE:
            score += 5
            reasons.append("posting text indicates OPT/F-1 or visa compatibility")
        elif sponsorship == SponsorshipAssessment.LIKELY_NOT_COMPATIBLE:
            score -= 30
            concerns.append("posting text indicates no sponsorship or restricted work authorization")
        else:
            concerns.append("OPT/F-1 and future sponsorship are not stated")

    if degree == DegreeAssessment.PHD_PREFERRED:
        concerns.append("PhD is preferred but not required")
    elif degree == DegreeAssessment.PHD_ACCEPTABLE:
        reasons.append("degree requirement includes a non-PhD path")

    if required_experience_years is not None and required_experience_years > 1:
        score -= min(30, (required_experience_years - 1) * 5)
        concerns.append(f"states at least {required_experience_years} years of experience")
    if title_seniority in {"mid", "senior"}:
        score -= 35
        concerns.append(f"title seniority appears {title_seniority}")
    if degree == DegreeAssessment.PHD_REQUIRED:
        score -= 70
        concerns.append("PhD is required")
    if any(term in title for term in profile.exclude_title_terms):
        score -= 30
        concerns.append("title contains a non-target or senior marker")

    return MatchResult(
        score=max(0, min(100, score)),
        seniority=seniority,
        title_seniority=title_seniority,
        title_seniority_priority=title_seniority_priority(title_seniority),
        us_location=us_location,
        location_region=location_region,
        preferred_location=preferred_location,
        sponsorship=sponsorship,
        degree=degree,
        matched_skills=skill_matches,
        matched_domains=domain_matches,
        reasons=tuple(dict.fromkeys(reasons)),
        concerns=tuple(dict.fromkeys(concerns)),
        exclusion_reasons=tuple(dict.fromkeys(exclusion_reasons)),
        required_experience_years=required_experience_years,
        entry_level_eligible=entry_level_eligible,
        eligible=eligible,
        career_track=classify_career_track(job.title, job.description),
    )
