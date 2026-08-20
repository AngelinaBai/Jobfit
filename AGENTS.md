# JobFit development rules

## Scope and authority

- The repository root is the only authoritative JobFit source tree.
- Application code lives in `src/jobfit`, tests live in `tests`, and browser-extension code lives in `browser-extension`.
- Do not create or maintain a second editable source tree inside the repository.
- Preserve `.env`, PostgreSQL credentials, and the Docker data volume. Never print secrets or commit local configuration.
- Keep the package, FastAPI application, templates, browser extension, README, and release documentation on the same version.

## Development workflow

- Target Python 3.12 or newer and preserve SQLAlchemy 2.x typing and patterns.
- Add or update tests for behavioral changes. Run the complete test suite before handoff.
- Keep schema changes backward-compatible with existing PostgreSQL data. Prefer explicit, idempotent migrations until a migration framework is introduced.
- Do not commit generated caches, local databases, logs, virtual environments, or release archives.
- Treat the personalized matching profile and eligibility rules as product behavior; change them only with explicit product direction and regression tests.

## Connector compliance

- Connect only to public job-board APIs and publicly accessible career pages.
- Do not bypass authentication, login walls, CAPTCHAs, MFA, robots/access controls, rate limits, or anti-bot protections.
- Do not reuse personal browser sessions, cookies, credentials, or authenticated portal data for automatic scans.
- LinkedIn, Handshake, 12twenty, and other login-required portals must remain user-initiated browser-assisted imports.
- Use descriptive, truthful user agents and bounded request timeouts.
- Prefer documented public ATS APIs. Generic HTML parsing and Playwright rendering are fallbacks for public pages only.
- Keep request volume conservative. Avoid unnecessary repeated detail-page fetches and unbounded crawling.
- Normalize every connector result into `NormalizedJob`; validate required identifiers, titles, and URLs before persistence.
- Preserve per-source/external-ID deduplication and content hashing so rescans are idempotent.
- Record scan failures without discarding prior jobs or application history.
- Never mark unseen jobs inactive or delete them merely because a single remote scan failed or returned incomplete data.

## Application and source safety

- Application records and their associated jobs are user data and must not be lost during source maintenance.
- Deleting a monitored source may delete untracked jobs, but tracked jobs must first move to the disabled local archive source.
- Browser-import, manual, and archive sources are managed automatically and must not be exposed to destructive source-management actions.
