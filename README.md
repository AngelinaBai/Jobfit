# JobFit v0.9.0

Created by **Angelina Bai**.

JobFit is a local job-discovery and application-tracking system. It collects public job postings, ranks them against a personalized early-career profile, and stores job-search progress in PostgreSQL.

## v0.9.0 highlights

- **Today ranking:** the default view now combines personalized fit, early-career signals, and a meaningful freshness boost.
- **Balanced career tracks:** every recommendation is classified as Tech, Quant, or Adjacent, with dedicated filters and a combined default view.
- **Broader opportunity set:** additional verified startup, mid-sized technology, and quantitative-firm sources expand beyond large employers.
- **Verified source onboarding:** JobFit extracts and validates individual jobs before a source enters the watchlist; zero results are reported as inconclusive rather than successful.

## v0.8.1 foundation

- **Rendered public listings:** host-aware extraction for Jane Street, Google Careers, Meta Careers, and Riot Games.
- **Stable job identity:** public listing URLs provide durable external IDs and prevent duplicate desktop/mobile cards.
- **Safer generic fallback:** recognized listing cards are used before bounded detail-page crawling, avoiding unrelated navigation pages and false jobs.

- **Separate Applications page:** job discovery and application tracking are now distinct workflows.
- **Manual application entry:** record applications from LinkedIn, Handshake, referrals, recruiters, or any job JobFit did not discover.
- **Automatic workflow transition:** once a discovered job is marked Applied, Assessment, Interview, Offer, Rejected, or Withdrawn, it disappears from the Jobs page and remains in Applications.
- **Saved jobs stay discoverable:** Saved postings remain on Jobs with a Saved badge.
- **Not interested:** dismiss any unwanted posting from recommendations without deleting its source or job record; rescans keep it dismissed.
- **Application tracker:** filter by company/role/status, update status, resume version, and notes, and reopen the original posting.
- **Application metrics:** total tracked, applied, assessments, interviews, offers, and rejected counts.
- **Company Watchlist:** paste a public company career-page URL and let JobFit detect supported ATS sources or use its rendered-page fallback.
- **Source management:** edit, enable or disable, rescan, and safely delete monitored sources. Deletion preserves tracked jobs in a local archive source.
- **Preferred regions:** United States, China, and Singapore remain in scope.
- **Experience-aware ranking:** stated experience requirements lower a job's score but never exclude it by themselves, including when they appear under preferred qualifications.
- **Hard eligibility checks:** PhD-required roles and clearly mid/senior titles are excluded from default recommendations.

## Upgrade

From the project directory:

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m playwright install chromium
set -a
source .env
set +a
pytest
jobfit-web
```

Your existing PostgreSQL jobs and applications are preserved.

## Public portfolio deployment

JobFit is designed to use GitHub for source control and Render for the running
FastAPI service, PostgreSQL database, and scheduled scans. The included
`render.yaml` provisions:

- a Docker-based web service with a `/healthz` health check;
- a private Render PostgreSQL 17 database;
- a scanner cron job that refreshes enabled public sources every six hours; and
- production public mode with administrator authentication for private data and
  every write operation.

In public mode, visitors can browse live job recommendations and matching
explanations. They cannot view Applications, manage sources, import jobs, save or
dismiss listings, or start scans. Use the **Admin** link and the credentials set
in Render to access those controls.

### Deploy from GitHub

1. Create a GitHub repository and push this project. Do not add `.env`; it is
   ignored and must remain local.
2. In Render, choose **New → Blueprint**, connect the GitHub repository, and
   select the repository's `render.yaml`.
3. When prompted for `ADMIN_PASSWORD`, enter a long unique password. Keep
   `ADMIN_USERNAME=admin`, or change it in Render after provisioning.
4. Review the proposed paid resources before applying the Blueprint. The
   reliable résumé configuration uses a Starter web service, Starter cron job,
   and Basic PostgreSQL database.
5. After the first deploy, trigger `jobfit-scan` once in Render to populate the
   hosted database. Browser refreshes then show the latest stored results, while
   the cron job refreshes the data automatically.
6. Add the Render URL to the GitHub repository description and your résumé.

GitHub Actions runs the complete test suite for pushes and pull requests. Render
deploys only after those checks pass.

### Production environment variables

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Render injects the private PostgreSQL connection string. |
| `PUBLIC_MODE=true` | Enables the public read-only/private-admin boundary. |
| `ADMIN_USERNAME` | Username for private features. |
| `ADMIN_PASSWORD` | Required secret; never commit it. |
| `HTTP_TIMEOUT_SECONDS` | Bounded timeout for public connector requests. |

The public database starts empty. Migrating local job/application history is
optional, but personal application records should not be copied into a public
portfolio deployment unless the administrator boundary has been reviewed and
tested first.

## Web workflow

Start JobFit:

```bash
jobfit-web
```

Open `http://127.0.0.1:8000`.

### Jobs

Use the Jobs page to discover and evaluate postings. Each card has:

- Open application
- Save
- Mark applied

When you click **Mark applied**, the job moves out of discovery and into the Applications page.

### Applications

Open `http://127.0.0.1:8000/applications` or click **Applications** in the navigation.

You can manually enter:

- Company
- Job title
- Location
- Job URL
- Status
- Application date
- Source
- Resume used
- Notes

Manual applications are stored in the tracker but do not appear as search recommendations.

## Automatic career-page discovery

Under **Company Watchlist**, enter a company name and public careers URL. JobFit detects Greenhouse, Lever, and Ashby where possible and uses a Playwright-rendered public-page fallback for JavaScript-heavy sites.

JobFit does not bypass logins, CAPTCHAs, MFA, or access controls.

## Tests

```bash
pytest
```

Current release: **73 tests passing**.

## License

MIT License. Copyright (c) 2026 Angelina Bai.
