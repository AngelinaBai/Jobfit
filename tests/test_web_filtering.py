from jobfit.services.filtering import matches_terms


def test_data_keyword_matches_data_title():
    assert matches_terms("Data Scientist", ["data"])


def test_data_keyword_does_not_match_ai_title_without_data():
    assert not matches_terms("AI Builder Intern", ["data"])


def test_ai_does_not_match_paid_or_training_substrings():
    assert not matches_terms("Paid Media Analyst", ["ai"])
    assert matches_terms("AI Engineer", ["ai"])
