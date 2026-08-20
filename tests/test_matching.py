from datetime import UTC, datetime

from jobfit.models import Job
from jobfit.services.matching import CareerTrack, SponsorshipAssessment, assess_sponsorship, score_job


def make_job(*, title: str, description: str, location: str = "New York, NY") -> Job:
    return Job(
        external_job_id="x",
        source_id=1,
        title=title,
        company="Example",
        location=location,
        description=description,
        job_url="https://example.com/job",
        date_posted=datetime.now(UTC),
        date_discovered=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        content_hash="a" * 64,
        status="active",
    )


def test_sponsorship_negative_phrase_wins() -> None:
    text = "Applicants must be authorized to work in the US without sponsorship."
    assert assess_sponsorship(text) == SponsorshipAssessment.LIKELY_NOT_COMPATIBLE


def test_sponsorship_positive_phrase() -> None:
    text = "We welcome STEM OPT candidates and provide H-1B sponsorship."
    assert assess_sponsorship(text) == SponsorshipAssessment.LIKELY_COMPATIBLE


def test_sponsorship_unknown_when_not_stated() -> None:
    assert assess_sponsorship("Python and SQL required") == SponsorshipAssessment.UNKNOWN


def test_resume_fit_scores_relevant_entry_role_highly() -> None:
    job = make_job(
        title="Entry Level Data Scientist",
        description=(
            "Use Python, SQL, pandas, machine learning, statistical modeling and XGBoost. "
            "Master's degree in data science, applied mathematics, or financial engineering preferred. "
            "STEM OPT candidates are welcome."
        ),
    )
    result = score_job(job)
    assert result.score >= 75
    assert result.seniority == "entry"
    assert result.sponsorship == SponsorshipAssessment.LIKELY_COMPATIBLE


def test_senior_non_us_role_is_penalized() -> None:
    job = make_job(
        title="Senior Sales Manager",
        description="Lead enterprise sales.",
        location="London, UK",
    )
    result = score_job(job)
    assert result.score < 25
    assert result.us_location is False


def test_internal_word_does_not_classify_as_intern() -> None:
    job = make_job(
        title="AI Deployment Manager",
        description="Manage internal stakeholders and requires 7+ years of experience.",
    )
    result = score_job(job)
    assert result.seniority == "senior"
    assert result.required_experience_years == 7
    assert result.entry_level_eligible is False
    assert result.eligible is False
    assert result.score < 45


def test_explicit_seven_year_requirement_overrides_role_keyword_score() -> None:
    job = make_job(
        title="Machine Learning Engineer",
        description=(
            "Use Python, SQL, pandas, machine learning and XGBoost. "
            "Applicants must have at least 7 years of professional experience."
        ),
    )
    result = score_job(job)
    assert result.required_experience_years == 7
    assert result.seniority == "senior"
    assert result.score < 45


def test_two_year_requirement_lowers_score_without_exclusion() -> None:
    job = make_job(
        title="Data Scientist",
        description="Requires 2 years of experience using Python and SQL.",
    )
    result = score_job(job)
    assert result.required_experience_years == 2
    assert result.entry_level_eligible is True
    assert result.eligible is True
    assert result.seniority == "mid"


def test_preferred_five_year_requirement_lowers_score_without_exclusion() -> None:
    job = make_job(
        title="People Research Scientist, Recruiting",
        description=(
            "Preferred Qualifications: 5+ years of experience in research, people analytics, "
            "or related quantitative fields with demonstrated research methodology expertise."
        ),
    )
    result = score_job(job)
    assert result.required_experience_years == 5
    assert result.entry_level_eligible is True
    assert result.eligible is True
    assert result.exclusion_reasons == ()
    assert "states at least 5 years of experience" in result.concerns


def test_title_signal_new_grad_is_explicit_entry_priority() -> None:
    job = make_job(
        title="Data Scientist, New Graduate",
        description="Use Python and SQL. No prior full-time experience required.",
    )
    result = score_job(job)
    assert result.title_seniority == "new-grad"
    assert result.title_seniority_priority == 5
    assert result.seniority == "entry"


def test_unknown_title_has_lower_priority_than_entry_title() -> None:
    unknown = score_job(make_job(title="Solutions Architect - AI", description="Use Python and SQL."))
    entry = score_job(make_job(title="Entry Level Data Scientist", description="Use Python and SQL."))
    assert entry.title_seniority_priority > unknown.title_seniority_priority


def test_experience_requirement_overrides_intern_title() -> None:
    job = make_job(
        title="Machine Learning Intern",
        description="Requires 5+ years of professional machine learning experience.",
    )
    result = score_job(job)
    assert result.title_seniority == "intern"
    assert result.seniority == "senior"
    assert result.entry_level_eligible is True
    assert result.eligible is True

from jobfit.services.matching import DegreeAssessment, assess_degree_requirement, classify_location


def test_phd_required_role_is_hard_excluded() -> None:
    job = make_job(
        title="Machine Learning Research Scientist",
        description="Requirements: PhD in Computer Science or equivalent experience. Use Python and ML.",
    )
    result = score_job(job)
    assert result.degree == DegreeAssessment.PHD_REQUIRED
    assert result.eligible is False
    assert "PhD required" in result.exclusion_reasons


def test_ms_or_phd_is_not_phd_only() -> None:
    assessment = assess_degree_requirement(
        "Data Scientist",
        "Candidates should have a Master's or PhD in statistics, computer science, or a related field.",
    )
    assert assessment == DegreeAssessment.PHD_ACCEPTABLE


def test_china_and_singapore_are_preferred_locations() -> None:
    china = score_job(make_job(title="Data Analyst, New Grad", description="Use Python and SQL.", location="Shanghai, China"))
    singapore = score_job(make_job(title="Machine Learning Intern", description="Use Python.", location="Singapore"))
    assert china.location_region == "china" and china.preferred_location and china.eligible
    assert singapore.location_region == "singapore" and singapore.preferred_location and singapore.eligible


def test_us_sponsorship_conflict_is_hard_exclusion_but_not_for_singapore() -> None:
    text = "Applicants must be authorized to work in the US without sponsorship. Use Python and SQL."
    us = score_job(make_job(title="Data Analyst, New Grad", description=text, location="New York, NY"))
    sg = score_job(make_job(title="Data Analyst, New Grad", description=text, location="Singapore"))
    assert us.eligible is False
    assert sg.eligible is True


def test_hrt_quant_research_graduate_title_is_recommended() -> None:
    job = make_job(
        title="Algorithm Developer (Quant Research & Trading) – 2027 Grads",
        location="New York | Singapore | London",
        description="New Grad strategy development role for quantitative thinkers.",
    )
    result = score_job(job)
    assert result.title_seniority == "new-grad"
    assert result.score >= 45
    assert result.eligible is True
    assert result.career_track == CareerTrack.QUANT


def test_machine_learning_role_is_classified_as_tech() -> None:
    result = score_job(make_job(title="Machine Learning Engineer, New Grad", description="Python and SQL"))
    assert result.career_track == CareerTrack.TECH


def test_general_software_engineering_is_a_target_tech_role() -> None:
    result = score_job(make_job(title="Software Engineer", description="Public career listing."))
    assert result.career_track == CareerTrack.TECH
    assert result.score >= 25
