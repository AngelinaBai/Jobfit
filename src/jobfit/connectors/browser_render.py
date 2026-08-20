from __future__ import annotations


class BrowserRenderError(RuntimeError):
    pass


def render_public_page(url: str, *, timeout_seconds: float = 20.0) -> tuple[str, str]:
    """Render a public page with headless Chromium and return (final_url, html).

    This is a fallback for JavaScript-driven public career sites. It does not
    reuse personal browser sessions, bypass authentication, or solve CAPTCHAs.
    """
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - dependency should be installed
        raise BrowserRenderError(
            "Playwright is not installed. Reinstall JobFit v0.9.0 dependencies."
        ) from exc

    timeout_ms = max(1_000, int(timeout_seconds * 1000))
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    user_agent="JobFit/0.9.0 (+public-career-page-renderer)",
                    viewport={"width": 1440, "height": 1000},
                )
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8_000))
                except PlaywrightError:
                    # Many career sites keep analytics/network connections open.
                    # DOM content is still useful after a short settling period.
                    page.wait_for_timeout(1_500)
                return page.url, page.content()
            finally:
                browser.close()
    except PlaywrightError as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message.lower():
            raise BrowserRenderError(
                "The JobFit browser engine is not installed. Run: python -m playwright install chromium"
            ) from exc
        raise BrowserRenderError(f"Could not render public career page: {exc}") from exc
