# Base image ships a Python runtime with a Chromium build matching a
# specific Playwright release already installed -- no separate
# `playwright install` step (and its large download) is needed at build
# time. The tag's version MUST match the "playwright" pin in
# requirements.txt. This project pins playwright==1.56.0; if you bump that
# pin, bump this tag to match (see https://playwright.dev/python/docs/docker
# for the current list of published tags -- this could not be verified from
# the sandboxed environment that built this project, since it has no
# outbound access to mcr.microsoft.com. Verify it resolves before your
# first `docker build`, and swap to the correct tag if not).
FROM mcr.microsoft.com/playwright/python:v1.56.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dog_monitor ./dog_monitor

ENV PYTHONUNBUFFERED=1 \
    HEADLESS=true \
    LOG_LEVEL=INFO

# Cloud Run Jobs runs this container to completion once per execution and
# expects a clean, non-zero-only-on-fatal-error exit -- see dog_monitor/main.py.
ENTRYPOINT ["python", "-m", "dog_monitor.main"]
