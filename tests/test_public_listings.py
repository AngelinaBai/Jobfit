from jobfit.connectors.public_listings import extract_public_listing_jobs


def test_jane_street_rendered_listing_extracts_real_roles_and_deduplicates() -> None:
    html = """
    <main>
      <a href="/join-jane-street/position/8573523002/">
        Quantitative Trader\nFull-Time: New Grad\nNew York\nTrading, Research, and Machine Learning\nPermanent
      </a>
      <div class="mobile">
        <a href="/join-jane-street/position/8573523002/">
          Quantitative Trader\nFull-Time: New Grad\nNew York\nTrading, Research, and Machine Learning\nPermanent
        </a>
      </div>
      <a href="/join-jane-street/position/8498547002/">
        Quantitative Researcher\nInternship\nNew York\nTrading, Research, and Machine Learning\nMay-August
      </a>
      <a href="/join-jane-street/closed-internship/old-role/">
        Old Role (not currently accepting applications)
      </a>
    </main>
    """
    jobs = extract_public_listing_jobs(
        html,
        "https://www.janestreet.com/join-jane-street/open-roles/",
        "Jane Street",
    )
    assert [job.external_job_id for job in jobs] == ["8573523002", "8498547002"]
    assert jobs[0].title == "Quantitative Trader — New Grad"
    assert jobs[0].location == "New York"
    assert "New Grad" in jobs[0].description


def test_google_rendered_card_extracts_heading_location_and_qualifications() -> None:
    html = """
    <div class="result-card">
      <h3>Research Data Scientist, Ads Metrics</h3>
      <span class="r0wTof">New York, NY, USA</span>
      <div class="Xsxa1e"><h4>Minimum qualifications</h4><ul><li>Master's degree.</li></ul></div>
      <a href="/about/careers/applications/jobs/results/124625707799061190-research-data-scientist"></a>
    </div>
    """
    jobs = extract_public_listing_jobs(
        html,
        "https://www.google.com/about/careers/applications/jobs/results/",
        "Google",
    )
    assert len(jobs) == 1
    assert jobs[0].external_job_id == "124625707799061190"
    assert jobs[0].title == "Research Data Scientist, Ads Metrics"
    assert jobs[0].location == "New York, NY, USA"
    assert "Minimum qualifications" in jobs[0].description


def test_google_current_relative_card_url_is_resolved_without_duplicate_path() -> None:
    html = """
    <div class="result-card">
      <h3>Software Engineer, Early Career</h3>
      <span class="r0wTof">New York, NY, USA</span>
      <div><h4>Minimum qualifications</h4><p>Bachelor's degree and Python.</p></div>
      <a href="jobs/results/123456-software-engineer-early-career"></a>
    </div>
    """
    jobs = extract_public_listing_jobs(
        html,
        "https://www.google.com/about/careers/applications/jobs/results/",
        "Google",
    )
    assert len(jobs) == 1
    assert jobs[0].external_job_id == "123456"
    assert jobs[0].job_url == (
        "https://www.google.com/about/careers/applications/jobs/results/"
        "123456-software-engineer-early-career"
    )


def test_meta_rendered_card_extracts_profile_job_details_link() -> None:
    html = """
    <a href="/profile/job_details/2851019931950200" role="link">
      <div><h3>Data Scientist, Product Analytics</h3></div>
      <div>Menlo Park, CA +2 locations</div><div>⋅</div><div>Data &amp; Analytics</div>
    </a>
    """
    jobs = extract_public_listing_jobs(html, "https://www.metacareers.com/jobsearch/", "Meta")
    assert len(jobs) == 1
    assert jobs[0].external_job_id == "2851019931950200"
    assert jobs[0].title == "Data Scientist, Product Analytics"
    assert jobs[0].location == "Menlo Park, CA +2 locations"


def test_riot_rendered_row_extracts_semantic_columns() -> None:
    html = """
    <a href="/en/j/7844349" class="job-row__inner js-job-url">
      <div class="job-row__col job-row__col--primary">Staff Software Engineer</div>
      <div class="job-row__col job-row__col--secondary">Software Engineering Group</div>
      <div class="job-row__col job-row__col--secondary">Riot Operations &amp; Support</div>
      <div class="job-row__col job-row__col--secondary">Los Angeles, USA</div>
    </a>
    """
    jobs = extract_public_listing_jobs(
        html, "https://www.riotgames.com/en/work-with-us/jobs", "Riot Games"
    )
    assert len(jobs) == 1
    assert jobs[0].external_job_id == "7844349"
    assert jobs[0].title == "Staff Software Engineer"
    assert jobs[0].location == "Los Angeles, USA"
    assert "Software Engineering Group" in jobs[0].description


def test_hrt_rendered_cards_extract_real_roles_and_ignore_apply_link_duplicates() -> None:
    html = """
    <div class="hrt-card-item" data-jobid="569">
      <div class="hrt-card-title-wrap">
        <a class="hrt-card-title" href="/hrt-job/algorithm-developer-quant-researcher-2027-grads/">
          Algorithm Developer (Quant Research &amp; Trading) – 2027 Grads
        </a>
        <a class="hrt-card-button" href="/hrt-job/algorithm-developer-quant-researcher-2027-grads/">↳ Apply Now</a>
      </div>
      <div class="hrt-card-meta-desktop">
        <ul class="hrt-card-info-list"><li>New York</li><li>Singapore</li><li>London</li></ul>
        <ul class="hrt-card-info-list second-list"><li>Strategy Development</li><li>New Grad</li></ul>
      </div>
      <p>Exceptional quantitative thinkers join our Algorithm Development teams.</p>
    </div>
    """
    jobs = extract_public_listing_jobs(
        html, "https://www.hudsonrivertrading.com/careers/", "Hudson River Trading"
    )
    assert len(jobs) == 1
    assert jobs[0].external_job_id == "algorithm-developer-quant-researcher-2027-grads"
    assert jobs[0].title == "Algorithm Developer (Quant Research & Trading) – 2027 Grads"
    assert jobs[0].location == "New York | Singapore | London"
    assert "Exceptional quantitative thinkers" in jobs[0].description


def test_unknown_host_is_not_parsed_by_host_specific_rules() -> None:
    html = '<a href="/jobs/123"><h3>Data Scientist</h3></a>'
    assert extract_public_listing_jobs(html, "https://example.com/careers", "Example") == []
