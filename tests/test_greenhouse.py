from __future__ import annotations

import requests
import pytest

from jobfit.connectors.greenhouse import ConnectorError, GreenhouseConnector


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.last_call: dict | None = None

    def get(self, url: str, **kwargs):
        self.last_call = {"url": url, **kwargs}
        if self.error:
            raise self.error
        return self.response


def test_fetch_and_normalize_jobs() -> None:
    fake_session = FakeSession(
        FakeResponse(
            {
                "jobs": [
                    {
                        "id": 123,
                        "title": "Quantitative Analyst",
                        "absolute_url": "https://example.com/jobs/123",
                        "location": {"name": "New York, NY"},
                        "content": "Build &amp; test models.",
                        "updated_at": "2026-08-06T12:00:00-04:00",
                    }
                ]
            }
        )
    )
    connector = GreenhouseConnector(session=fake_session)

    jobs = connector.fetch_jobs(source_identifier="example", company_name="Example Capital")

    assert len(jobs) == 1
    assert jobs[0].external_job_id == "123"
    assert jobs[0].company == "Example Capital"
    assert jobs[0].description == "Build & test models."
    assert len(jobs[0].content_hash) == 64
    assert fake_session.last_call["params"] == {"content": "true"}


def test_timeout_becomes_connector_error() -> None:
    connector = GreenhouseConnector(session=FakeSession(error=requests.Timeout()))

    with pytest.raises(ConnectorError, match="timed out"):
        connector.fetch_jobs(source_identifier="example", company_name="Example")


def test_invalid_shape_is_rejected() -> None:
    connector = GreenhouseConnector(session=FakeSession(FakeResponse({"unexpected": []})))

    with pytest.raises(ConnectorError, match="jobs list"):
        connector.fetch_jobs(source_identifier="example", company_name="Example")
