from jobfit.services.filtering import matches_terms
from jobfit.profile import ANGELINA_PROFILE, DEFAULT_JOB_QUERY_TERMS


def test_data_keyword_matches_data_title():
    assert matches_terms("Data Scientist", ["data"])


def test_data_keyword_does_not_match_ai_title_without_data():
    assert not matches_terms("AI Builder Intern", ["data"])


def test_ai_does_not_match_paid_or_training_substrings():
    assert not matches_terms("Paid Media Analyst", ["ai"])
    assert matches_terms("AI Engineer", ["ai"])


def test_quantitative_trader_requires_an_explicit_default_phrase():
    assert not matches_terms("Quantitative Trader - Entry Level", ["quant"])
    assert matches_terms(
        "Quantitative Trader - Entry Level", ["quantitative trader"]
    )


def test_default_query_covers_every_target_role_and_core_data_titles():
    assert set(ANGELINA_PROFILE.target_roles).issubset(DEFAULT_JOB_QUERY_TERMS)
    for title in (
        "Quantitative Analyst",
        "Data Analyst",
        "Data Scientist",
        "Data Engineer",
        "Analytics Engineer",
        "Business Intelligence Analyst",
        "Data Science Intern",
        "Data Engineering Intern",
        "Data Analytics Associate",
    ):
        assert matches_terms(title, DEFAULT_JOB_QUERY_TERMS)
