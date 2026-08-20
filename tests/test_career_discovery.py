from __future__ import annotations

from jobfit.connectors.career_page import CareerPageConnector
from jobfit.services.career_discovery import discover_career_source


class FakeResponse:
    def __init__(self, text: str, url: str = "https://example.com/careers"):
        self.text = text
        self.url = url
    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
    def get(self, *args, **kwargs):
        return self.responses.pop(0)


def test_discovers_greenhouse_link_from_company_career_page():
    html = '<a href="https://job-boards.greenhouse.io/exampleco">Open roles</a>'
    result = discover_career_source(
        "https://example.com/careers",
        session=FakeSession([FakeResponse(html)]),
    )
    assert result.source_type == "greenhouse"
    assert result.source_identifier == "exampleco"


def test_discovers_embedded_greenhouse_board_token():
    html = '<iframe src="https://boards.greenhouse.io/embed/job_board?for=exampleco"></iframe>'
    result = discover_career_source(
        "https://example.com/careers",
        session=FakeSession([FakeResponse(html)]),
    )
    assert result.source_type == "greenhouse"
    assert result.source_identifier == "exampleco"


def test_greenhouse_structural_paths_are_not_board_tokens(monkeypatch):
    import jobfit.services.career_discovery as mod

    monkeypatch.setattr(
        mod,
        "render_public_page",
        lambda url, timeout_seconds: (url, "<html><body>Open roles</body></html>"),
    )
    html = """
    <script src="https://boards.greenhouse.io/embed/job_board/js?for="></script>
    <script>const api = "https://boards-api.greenhouse.io/v1/boards/";</script>
    """
    result = discover_career_source(
        "https://example.com/careers",
        session=FakeSession([FakeResponse(html)]),
    )
    assert result.source_type == "career_page"
    assert result.source_identifier == "https://example.com/careers"


def test_falls_back_to_generic_public_career_page():
    result = discover_career_source(
        "https://example.com/careers",
        session=FakeSession([FakeResponse("<html><body>Careers</body></html>")]),
    )
    assert result.source_type == "career_page"
    assert result.source_identifier == "https://example.com/careers"


def test_generic_connector_reads_jobposting_jsonld():
    html = '''
    <html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting","title":"Data Scientist, New Grad",
     "description":"Use Python and SQL.","datePosted":"2026-08-01",
     "jobLocation":{"@type":"Place","address":{"addressLocality":"New York","addressRegion":"NY","addressCountry":"US"}},
     "url":"https://example.com/jobs/1","identifier":{"value":"job-1"}}
    </script></head><body></body></html>
    '''
    connector = CareerPageConnector(session=FakeSession([FakeResponse(html)]))
    jobs = connector.fetch_jobs(source_identifier="https://example.com/careers", company_name="Example")
    assert len(jobs) == 1
    assert jobs[0].title == "Data Scientist, New Grad"
    assert jobs[0].location == "New York, NY, US"


def test_direct_workday_url_uses_generic_public_parser():
    result = discover_career_source("https://example.wd1.myworkdayjobs.com/External")
    assert result.source_type == "career_page"
    assert "Workday" in result.detail


def test_discovery_uses_rendered_html_when_static_page_has_no_ats(monkeypatch):
    from types import SimpleNamespace
    import jobfit.services.career_discovery as mod

    class FakeSession:
        def get(self, *args, **kwargs):
            return SimpleNamespace(
                url="https://example.com/careers",
                text="<html><body><div id='app'></div></body></html>",
                raise_for_status=lambda: None,
            )

    monkeypatch.setattr(
        mod,
        "render_public_page",
        lambda url, timeout_seconds: (
            url,
            '<a href="https://jobs.lever.co/exampleco/abc">Data Scientist</a>',
        ),
    )
    result = mod.discover_career_source(
        "https://example.com/careers", session=FakeSession()
    )
    assert result.source_type == "lever"
    assert result.source_identifier == "exampleco"
    assert "JavaScript" in result.detail


def test_career_page_connector_renders_root_when_static_scan_is_empty(monkeypatch):
    from types import SimpleNamespace
    import jobfit.connectors.career_page as mod

    class FakeSession:
        def get(self, url, **kwargs):
            return SimpleNamespace(
                url=url,
                text="<html><body><div id='app'></div></body></html>",
                raise_for_status=lambda: None,
            )

    rendered = '''
    <html><body>
      <script type="application/ld+json">
      {"@type":"JobPosting","title":"Data Scientist, New Grad","description":"Requirements: Python and SQL.","url":"https://example.com/jobs/1","datePosted":"2026-08-08","jobLocation":{"address":{"addressLocality":"New York","addressRegion":"NY","addressCountry":"US"}}}
      </script>
    </body></html>
    '''
    monkeypatch.setattr(mod, "render_public_page", lambda url, timeout_seconds: (url, rendered))
    connector = mod.CareerPageConnector(session=FakeSession())
    jobs = connector.fetch_jobs(source_identifier="https://example.com/careers", company_name="Example")
    assert len(jobs) == 1
    assert jobs[0].title == "Data Scientist, New Grad"


def test_supported_dynamic_host_skips_static_generic_false_positives(monkeypatch):
    from types import SimpleNamespace
    import jobfit.connectors.career_page as mod

    class JaneSession:
        def get(self, url, **kwargs):
            return SimpleNamespace(
                url=url,
                text='<a href="/join-jane-street/story/paths-with-purpose/">Paths with Purpose</a>',
                raise_for_status=lambda: None,
            )

    rendered = """
    <a href="/join-jane-street/position/8573523002/">
      Quantitative Trader\nFull-Time: New Grad\nNew York\nTrading, Research, and Machine Learning\nPermanent
    </a>
    """
    monkeypatch.setattr(mod, "render_public_page", lambda url, timeout_seconds: (url, rendered))
    connector = mod.CareerPageConnector(session=JaneSession())
    jobs = connector.fetch_jobs(
        source_identifier="https://www.janestreet.com/join-jane-street/open-roles/",
        company_name="Jane Street",
    )
    assert len(jobs) == 1
    assert jobs[0].external_job_id == "8573523002"
    assert jobs[0].title == "Quantitative Trader — New Grad"
