from jobfit.connectors.ashby import AshbyConnector
from jobfit.connectors.lever import LeverConnector


class Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class Session:
    def __init__(self, payload): self.payload = payload
    def get(self, *args, **kwargs): return Response(self.payload)


def test_lever_connector_normalizes_job():
    connector = LeverConnector(session=Session([{
        "id": "abc", "text": "Data Science Intern", "hostedUrl": "https://jobs.example/abc",
        "categories": {"location": "New York, NY"}, "descriptionPlain": "Python and SQL", "createdAt": 0
    }]))
    jobs = connector.fetch_jobs(source_identifier="example", company_name="Example")
    assert jobs[0].title == "Data Science Intern"
    assert jobs[0].location == "New York, NY"


def test_ashby_connector_normalizes_job():
    connector = AshbyConnector(session=Session({"jobs": [{
        "id": "xyz", "title": "Machine Learning Engineer, New Grad",
        "jobUrl": "https://jobs.example/xyz", "location": "San Francisco, CA",
        "descriptionPlain": "Python and ML", "publishedAt": "2026-01-01T00:00:00Z"
    }]}))
    jobs = connector.fetch_jobs(source_identifier="example", company_name="Example")
    assert jobs[0].title.startswith("Machine Learning Engineer")
    assert jobs[0].company == "Example"
