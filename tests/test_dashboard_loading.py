"""Regression coverage for bounded dashboard database and scoring work."""
from datetime import datetime, timedelta, timezone
import importlib.util
import inspect
from pathlib import Path

from sqlalchemy import func, select


def test_dashboard_bounds_candidates_without_removing_stored_jobs(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite+pysqlite:///:memory:')
    monkeypatch.setenv('PUBLIC_MODE', 'false')
    path = Path(__file__).parents[1] / 'src/jobfit/web.py'
    spec = importlib.util.spec_from_file_location('jobfit_dashboard_loading_test', path)
    web = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(web)
    now = datetime.now(timezone.utc)
    try:
        with web.SessionFactory() as session:
            source = web.JobSource(company_name='Example', source_type='greenhouse',
                                   source_identifier='example', enabled=True)
            session.add(source)
            session.flush()
            session.add_all([
                web.Job(source_id=source.id, external_job_id=str(index),
                        title=f'Software Engineer New Grad {index}', company='Example',
                        description='Python software engineer. Bachelor degree.',
                        location='New York', job_url=f'https://example.com/jobs/{index}',
                        content_hash=str(index).zfill(64), status='active', dismissed=False,
                        date_discovered=now - timedelta(seconds=index),
                        date_posted=now, last_seen_at=now)
                for index in range(600)
            ])
            session.commit()
        scored = []
        original_score = web.score_job

        def record_score(job):
            scored.append(job.external_job_id)
            return original_score(job)

        monkeypatch.setattr(web, 'score_job', record_score)
        arguments = dict(query='software engineer', location='', sponsorship='any',
                         region='all', eligibility='all', min_score=0, status='all',
                         limit=50, sort_mode='today', keyword_scope='title', career_track='all')
        if 'opportunity_type' in inspect.signature(web._get_dashboard_jobs).parameters:
            arguments['opportunity_type'] = 'new-grad'
        rows = web._get_dashboard_jobs(**arguments)
        assert len(rows) == 50
        assert len(scored) == 500
        assert '599' not in scored
        with web.SessionFactory() as session:
            assert session.scalar(select(func.count(web.Job.id))) == 600
    finally:
        web.engine.dispose()
