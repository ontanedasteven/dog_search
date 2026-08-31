# NOTE: this tag's Playwright/Chromium version must match the "playwright"
# pin in requirements.txt (currently playwright==1.55.0) -- Playwright's
# Python client and the Chromium build it drives are version-locked, so a
# mismatch fails at container startup with "Executable doesn't exist".
# If you bump the pin in requirements.txt, bump this tag to match.
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "dog_monitor.main"]
