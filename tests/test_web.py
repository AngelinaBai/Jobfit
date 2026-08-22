from pathlib import Path


def test_dashboard_template_exists():
    root = Path(__file__).parents[1]
    assert (root / "src/jobfit/templates/dashboard.html").exists()
    assert (root / "src/jobfit/static/style.css").exists()


def test_project_metadata_contains_author_and_web_command():
    root = Path(__file__).parents[1]
    text = (root / "pyproject.toml").read_text()
    assert 'version = "0.9.0"' in text
    manifest = (root / "browser-extension/manifest.json").read_text()
    assert '"version": "0.9.0"' in manifest
    assert 'name = "Angelina Bai"' in text
    assert 'jobfit-web = "jobfit.web:main"' in text
    assert (root / "LICENSE").exists()


def test_dashboard_has_title_only_keyword_scope_and_live_filtering():
    root = Path(__file__).parents[1]
    template = (root / "src/jobfit/templates/dashboard.html").read_text()
    assert 'value="title"' in template
    assert 'Job title only' in template
    assert 'form.requestSubmit()' in template
    assert 'value="today"' in template
    assert 'Tech + Quant' in template


def test_safari_bookmarklet_templates_and_routes_exist():
    root = Path(__file__).parents[1]
    safari = (root / "src/jobfit/templates/safari.html").read_text()
    review = (root / "src/jobfit/templates/import_review.html").read_text()
    web = (root / "src/jobfit/web.py").read_text()
    assert "Copy bookmarklet code" in safari
    assert "Save job to JobFit" in review
    assert '/bookmarklet/review' in web
    assert '/bookmarklet/save' in web
    assert 'javascript:' in web


def test_dashboard_has_company_watchlist_and_preferred_regions():
    root = Path(__file__).parents[1]
    template = (root / "src/jobfit/templates/dashboard.html").read_text()
    web = (root / "src/jobfit/web.py").read_text()
    assert "Add a public career page" in template
    assert "Analyze &amp; add" in template
    assert "U.S. + China + Singapore" in template
    assert "Excluded jobs" in template
    assert '/sources/discover' in web


def test_v072_has_separate_application_tracker_and_manual_entry():
    root = Path(__file__).parents[1]
    applications = (root / "src/jobfit/templates/applications.html").read_text()
    dashboard = (root / "src/jobfit/templates/dashboard.html").read_text()
    web = (root / "src/jobfit/web.py").read_text()
    assert "Add an application" in applications
    assert 'action="/applications/manual"' in applications
    assert 'href="/applications"' in dashboard
    assert '@app.get("/applications"' in web
    assert '@app.post("/applications/manual"' in web


def test_v072_jobs_page_hides_post_application_statuses():
    root = Path(__file__).parents[1]
    web = (root / "src/jobfit/web.py").read_text()
    assert "hidden_statuses" in web
    assert "ApplicationStatus.APPLIED.value" in web
    assert "ApplicationStatus.INTERVIEW.value" in web
    assert "if job.application and job.application.status in hidden_statuses" in web


def test_dashboard_supports_dismissing_unwanted_jobs():
    root = Path(__file__).parents[1]
    template = (root / "src/jobfit/templates/dashboard.html").read_text()
    web = (root / "src/jobfit/web.py").read_text()
    assert "Not interested" in template
    assert 'action="/jobs/{{ row.job.id }}/dismiss"' in template
    assert '@app.post("/jobs/{job_id}/dismiss")' in web
    assert "Job.dismissed.is_(False)" in web


def test_public_portfolio_mode_hides_private_controls_and_requires_admin():
    root = Path(__file__).parents[1]
    template = (root / "src/jobfit/templates/dashboard.html").read_text()
    web = (root / "src/jobfit/web.py").read_text()
    assert "Public portfolio demo" in template
    assert "{% if is_admin %}" in template
    assert "Personal application tracking and all data-changing controls are private" in template
    assert "protect_private_features" in web
    assert 'PRIVATE_GET_PATHS = {"/applications", "/safari"}' in web
    assert '@app.get("/healthz"' in web


def test_render_and_github_deployment_files_exist():
    root = Path(__file__).parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    blueprint = (root / "render.yaml").read_text()
    workflow = (root / ".github/workflows/ci.yml").read_text()
    scan_workflow = (root / ".github/workflows/scan.yml").read_text()
    assert "FROM python:3.12-slim" in dockerfile
    assert "USER jobfit" in dockerfile
    assert "jobfit-web" in blueprint
    assert "plan: free" in blueprint
    assert "type: cron" not in blueprint
    assert "databases:" not in blueprint
    assert "PUBLIC_MODE" in blueprint
    assert "ADMIN_PASSWORD" in blueprint
    assert "/healthz" in blueprint
    assert "pytest" in workflow
    assert "jobfit-scan --create-tables --seed-sources" in scan_workflow
    assert "secrets.DATABASE_URL" in scan_workflow
    assert "schedule:" in scan_workflow


def test_v072_dashboard_has_source_management_controls():
    root = Path(__file__).parents[1]
    template = (root / "src/jobfit/templates/dashboard.html").read_text()
    web = (root / "src/jobfit/web.py").read_text()
    assert "Edit source" in template
    assert "Delete source" in template
    assert "/toggle" in template
    assert "/scan" in template
    assert '@app.post("/sources/{source_id}/edit")' in web
    assert '@app.post("/sources/{source_id}/delete")' in web
    assert 'class="source-manager"' in template
    assert "sources|length" in template
    assert "Needs attention" in template
    assert "Verified ·" in template
    assert "no verified roles found" in template
    assert "Legacy scan · rescan to verify" in template
    assert "latest_scans|default({})" in template
