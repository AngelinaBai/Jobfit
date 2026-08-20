from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    target_roles: tuple[str, ...]
    preferred_locations: tuple[str, ...]
    skills: tuple[str, ...]
    domain_terms: tuple[str, ...]
    education_terms: tuple[str, ...]
    exclude_title_terms: tuple[str, ...]


ANGELINA_PROFILE = CandidateProfile(
    target_roles=(
        "quantitative analyst",
        "quantitative researcher",
        "quantitative research",
        "quant research",
        "algorithm developer",
        "quant developer",
        "data scientist",
        "data analyst",
        "machine learning",
        "ml engineer",
        "ai engineer",
        "software engineer",
        "software developer",
        "artificial intelligence",
        "research scientist",
        "risk analyst",
        "trading analyst",
        "financial analyst",
        "analytics",
    ),
    preferred_locations=(
        "united states",
        "remote - us",
        "remote, us",
        "new york",
        "san francisco",
        "bay area",
        "los angeles",
        "seattle",
        "boston",
        "chicago",
        "austin",
    ),
    skills=(
        "python",
        "sql",
        "pandas",
        "numpy",
        "postgresql",
        "mongodb",
        "r ",
        "java",
        "xgboost",
        "lstm",
        "machine learning",
        "statistical analysis",
        "data analysis",
        "data cleaning",
        "data visualization",
        "etl",
        "econometrics",
        "time series",
        "object-oriented",
    ),
    domain_terms=(
        "quantitative finance",
        "financial engineering",
        "risk management",
        "asset management",
        "trading",
        "market data",
        "portfolio",
        "derivatives",
        "statistical modeling",
        "research",
        "data engineering",
        "analytics",
        "artificial intelligence",
        "ai",
    ),
    education_terms=(
        "applied mathematics",
        "data science",
        "financial engineering",
        "master's",
        "masters",
        "bachelor's",
        "bachelors",
        "stem",
    ),
    exclude_title_terms=(
        "senior",
        "staff",
        "principal",
        "director",
        "manager",
        "lead",
        "head of",
        "vice president",
        "vp ",
        "counsel",
        "attorney",
        "sales",
        "account executive",
        "recruiter",
    ),
)
