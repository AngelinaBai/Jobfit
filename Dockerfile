FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY pyproject.toml LICENSE README.md ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 jobfit \
    && chown -R jobfit:jobfit /app /ms-playwright

USER jobfit

EXPOSE 8000

CMD ["sh", "-c", "uvicorn jobfit.web:app --host 0.0.0.0 --port ${PORT:-8000}"]
