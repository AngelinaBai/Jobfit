import asyncio
import base64
import importlib.util
from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite+pysqlite:///:memory:')
    monkeypatch.setenv('PUBLIC_MODE', 'true')
    monkeypatch.setenv('ADMIN_PASSWORD', 'test-password')
    monkeypatch.setenv('ADMIN_USERNAME', 'admin')
    spec = importlib.util.spec_from_file_location(
        'jobfit_admin_test', Path(__file__).parents[1] / 'src/jobfit/web.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    module.engine.dispose()


def request(web, path, method='GET', authenticated=False):
    headers = []
    if authenticated:
        headers = [(b'authorization', b'Basic ' + base64.b64encode(b'admin:test-password'))]
    return Request(dict(type='http', method=method, path=path, root_path='',
                        scheme='https', server=('testserver', 443), headers=headers,
                        query_string=b'', app=web.app))


def test_admin_jobs_challenges_when_browser_omits_credentials(web):
    async def next_handler(req):
        raise AssertionError('Private route must not be reached')
    result = asyncio.run(web.protect_private_features(request(web, '/admin/jobs'), next_handler))
    assert result.status_code == 401
    assert result.headers['www-authenticate'] == 'Basic realm="JobFit Admin"'
    assert '/admin/jobs' in {route.path for route in web.app.routes}


def test_public_home_remains_public(web):
    async def next_handler(req):
        return Response('public')
    result = asyncio.run(web.protect_private_features(request(web, '/'), next_handler))
    assert result.status_code == 200


@pytest.mark.parametrize('destination,expected', [
    ('/?message=Saved', '/admin/jobs?message=Saved'),
    ('/', '/admin/jobs'),
    ('/applications?message=Applied', '/applications?message=Applied'),
    ('https://example.com/', 'https://example.com/'),
])
def test_authenticated_write_redirects_stay_in_admin(web, destination, expected):
    async def next_handler(req):
        return RedirectResponse(destination, status_code=303)
    result = asyncio.run(web.protect_private_features(
        request(web, '/jobs/1/status', 'POST', True), next_handler))
    assert result.headers['location'] == expected


def test_private_navigation_and_filters_keep_admin_route(web):
    req = request(web, '/applications', authenticated=True)
    response = web.applications_page(req, status='all', query='', message=None)
    assert 'href="/admin/jobs">Jobs' in response.body.decode()
    arguments = dict(query='', location='', sponsorship='any', region='all',
                     eligibility='all', min_score=0, status='all', limit=50,
                     sort_mode='today', keyword_scope='title', career_track='all', message=None)
    import inspect
    if 'opportunity_type' in inspect.signature(web.dashboard).parameters:
        arguments['opportunity_type'] = 'new-grad'
    response = web.dashboard(request(web, '/admin/jobs', authenticated=True), **arguments)
    html = response.body.decode()
    assert 'action="/admin/jobs"' in html
    assert 'href="/admin/jobs?eligibility=' in html
    assert 'Scan all sources now' in html
    response = web.dashboard(request(web, '/'), **arguments)
    assert 'Scan all sources now' not in response.body.decode()
    assert 'href="/admin/jobs">Admin' in response.body.decode()
