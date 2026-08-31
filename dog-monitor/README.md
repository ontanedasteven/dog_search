# Dog Monitor

Scans four Miami-Dade / Broward animal-shelter adoption sources for Cairn
Terriers, Norwich Terriers, Norfolk Terriers (strong possible), and generic
small terriers (lower-confidence possible), and emails an alert when a new
match appears. Built to run as a **Google Cloud Run Job** on a schedule,
using **Firestore** as the only persistent state (the container itself is
stateless between executions).

## Architecture

- **Compute**: a single-container Cloud Run Job (`python -m dog_monitor.main`)
  that runs to completion once per execution and exits. No server, no long-
  running process.
- **State**: Firestore (four collections: `animals`, `sightings`,
  `source_runs`, `monitor_state`). This is the *only* thing that persists
  between runs -- the container's local filesystem is discarded after each
  execution.
- **Scheduling**: Cloud Scheduler triggers a Cloud Run Job execution **once
  per day**. The application itself enforces the true "once every 4 days"
  requirement: on each invocation it reads `monitor_state.last_successful_full_scan`
  from Firestore, and if fewer than 96 hours have elapsed it logs that the
  scan isn't due and exits successfully without scraping anything. This is a
  real rolling 96-hour window, not a calendar-based cron approximation (see
  `main.is_scan_due` / `FULL_SCAN_INTERVAL_HOURS`).
- **Scraping**: Playwright + Chromium (headless), one scraper module per
  source, sharing a small generic engine for the two Humane Society sites.
- **Alerts**: Gmail SMTP via `smtplib`, using an App Password from Secret
  Manager.

```
dog-monitor/
├── dog_monitor/
│   ├── config.py            # env-var configuration
│   ├── database.py          # Firestore-backed dedup/alert-state store
│   ├── matching.py          # breed classification + ID/weight extraction (pure, unit-tested)
│   ├── models.py            # Animal / MatchLevel / MatchResult dataclasses
│   ├── alerts.py            # Gmail SMTP email composition + sending
│   ├── logging_config.py    # stdlib logging setup
│   ├── main.py               # orchestration entry point
│   └── scrapers/
│       ├── base.py                # BaseScraper + generic pet-card engine
│       ├── humane_broward.py      # Humane Society of Broward County
│       ├── humane_miami.py        # Humane Society of Greater Miami
│       └── petconnect.py          # 24Petconnect (BRWD + MIAD agencies)
├── tests/                    # pytest suite (matching, Firestore dedup, petconnect URL parsing)
├── Dockerfile
├── requirements.txt
├── cloudbuild.yaml           # Cloud Build pipeline: build -> push -> update the Cloud Run Job
├── .env.example
└── README.md
```

## IMPORTANT: selectors were not verified against live sites

This project was built in a sandboxed environment with **no outbound network
access** to humanebroward.com, humanesocietymiami.org, or 24petconnect.com
(only package registries were reachable). The CSS selectors in
`scrapers/humane_broward.py`, `scrapers/humane_miami.py`, and the search-UI
selectors in `scrapers/petconnect.py` are best-effort guesses at common
shelter-site/24Petconnect markup patterns -- **they have not been confirmed
against the real rendered DOM.**

The scrapers are written defensively for this: each tries several candidate
selectors, and if none match, the source fails gracefully with a clear log
warning (`Could not locate any pet card elements...` / `No detail links
found...` / `Search workflow failed...`) and is recorded as a failed row in
`source_runs` -- it will **not** silently return wrong data, and it will
**not** stop the other three sources from running.

**Before relying on this in production**, run it once for real (see "Manual
test run" below), watch the logs, and if you see those warnings:

1. Open the page in a real browser, open devtools, and find the actual
   selector for the pet-card grid (Humane Society sites) or the search
   form's species filter / location field / submit button (24Petconnect).
2. Update `card_selectors` in the relevant `scrapers/*.py` file (Humane
   Society), or the candidate-selector tuples inside
   `PetConnectScraper._run_search` (24Petconnect).
3. Re-run and confirm `animals_scanned` and `matches_found` in the logs look
   sane.

## Local development and testing

### 1. Set up the environment

```bash
git clone <this-repo>
cd dog-monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment variables

```bash
cp .env.example .env
# edit .env: EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD (see Gmail App Password below)
```

### 3. Run the unit test suite (no GCP account needed)

```bash
pytest
```

The matching/ID/weight tests are pure Python. The database/dedup tests run
against an in-memory fake Firestore client (`tests/fakes.py`) that
implements the same `collection().document().get()/set()/update()` surface
`FirestoreStore` uses -- fast, deterministic, and requires no network or
credentials. This is intentionally *not* a full emulator (no transactions,
queries, or server timestamps); it validates dedup/alert logic, not
Firestore's own behavior.

### 4. (Recommended) Validate against the real Firestore emulator

Before your first deploy, also exercise the app against the actual
Firestore emulator, which behaves like real Firestore (requires the Google
Cloud SDK):

```bash
gcloud components install cloud-firestore-emulator
gcloud emulators firestore start --host-port=localhost:8080
```

In another terminal:

```bash
export FIRESTORE_EMULATOR_HOST=localhost:8080
export FIRESTORE_PROJECT_ID=demo-test   # any non-empty value works against the emulator
source venv/bin/activate
python -m dog_monitor.main
```

Because `FIRESTORE_EMULATOR_HOST` is set, the `google-cloud-firestore`
client automatically talks to the local emulator instead of real GCP --
no credentials required. Inspect what got written via the emulator's admin
UI (printed in its startup logs) or `gcloud firestore` commands pointed at
the emulator.

### 5. Manual test run against real sources

```bash
source venv/bin/activate
python -m dog_monitor.main
```

This performs one full scan of all four sources and prints/logs progress.
Set `HEADLESS=false` in `.env` to watch the browser while debugging
selectors.

## Gmail App Password

`EMAIL_PASSWORD` must be a Gmail **App Password**, not your normal account
password (Gmail rejects normal passwords for SMTP from third-party apps):

1. Enable 2-Step Verification on the Gmail account: https://myaccount.google.com/security
2. Go to https://myaccount.google.com/apppasswords
3. Create an app password (choose "Mail" / "Other"), copy the 16-character
   value, and use it as `EMAIL_PASSWORD`.

## Containerizing

```bash
docker build -t dog-monitor:local .
docker run --rm \
  -e EMAIL_FROM=you@gmail.com \
  -e EMAIL_TO=you@gmail.com \
  -e EMAIL_PASSWORD=xxxxxxxxxxxxxxxx \
  -e GOOGLE_CLOUD_PROJECT=your-gcp-project \
  -v "$HOME/.config/gcloud:/root/.config/gcloud:ro" \
  dog-monitor:local
```

(Mounting `~/.config/gcloud` lets the container use your local `gcloud auth
application-default login` credentials for a local Docker smoke test against
real Firestore. In Cloud Run itself, credentials come from the job's
attached service account automatically -- no mounting needed.)

The `Dockerfile`'s base image tag must match the `playwright` version pinned
in `requirements.txt` (currently `1.55.0`) so the bundled Chromium build
lines up -- if you bump one, bump the other. This repo's build environment
had no network access to `mcr.microsoft.com` to confirm the exact tag
string -- verify it resolves (`docker pull
mcr.microsoft.com/playwright/python:v1.55.0-noble`) before your first
build, and adjust to whatever tag Microsoft currently publishes for that
Playwright version if it doesn't.

`requirements.txt` also includes `google-cloud-secret-manager`. It is not
currently imported by any application code -- the deploy steps below use
Cloud Run's `--set-secrets` flag, which resolves Secret Manager secrets to
plain environment variables before the container starts, so `config.py`
just reads `os.getenv(...)` as usual. The dependency is there if you'd
rather have the app fetch secrets directly via the Secret Manager API at
runtime instead; that would need a small addition to `config.py` to call
it, which isn't wired up here.

### Building with Cloud Build directly

`cloudbuild.yaml` runs the unit test suite (aborting the whole build if any
test fails), then builds the image, pushes it to Artifact Registry tagged
with both `$SHORT_SHA` and `latest`, and updates the (already-created)
Cloud Run Job to use the `$SHORT_SHA`-tagged image -- useful once you've
done the one-time `gcloud run jobs create` below and want repeatable,
test-gated redeploys (manually or via a Cloud Build trigger on push):

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION=REGION,_REPO=dog-monitor-repo,_IMAGE_NAME=dog-monitor,_JOB_NAME=dog-monitor-job
```

The build service account needs `roles/run.developer` in addition to its
default Artifact Registry push permissions for the final "update the job"
step to succeed.

## Deploying to Google Cloud

Replace `PROJECT_ID` and `REGION` (e.g. `us-east1`) throughout.

### 1. One-time project setup

```bash
gcloud config set project PROJECT_ID

gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com

# Create the Firestore database (Native mode) if this project doesn't have one yet.
gcloud firestore databases create --location=REGION --type=firestore-native

gcloud artifacts repositories create dog-monitor-repo \
  --repository-format=docker \
  --location=REGION
```

### 2. Store the email credentials as secrets

```bash
printf '%s' 'you@gmail.com'        | gcloud secrets create dog-monitor-email-from     --data-file=-
printf '%s' 'you@gmail.com'        | gcloud secrets create dog-monitor-email-to       --data-file=-
printf '%s' 'xxxxxxxxxxxxxxxx'     | gcloud secrets create dog-monitor-email-password --data-file=-
```

### 3. Create a dedicated service account for the job

```bash
gcloud iam service-accounts create dog-monitor-runner \
  --display-name "Dog Monitor Cloud Run Job"

# Firestore read/write access
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:dog-monitor-runner@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# Access to the three secrets
for secret in dog-monitor-email-from dog-monitor-email-to dog-monitor-email-password; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:dog-monitor-runner@PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

### 4. Build and push the image

```bash
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT_ID/dog-monitor-repo/dog-monitor:latest
```

### 5. Create the Cloud Run Job

```bash
gcloud run jobs create dog-monitor-job \
  --image REGION-docker.pkg.dev/PROJECT_ID/dog-monitor-repo/dog-monitor:latest \
  --region REGION \
  --service-account dog-monitor-runner@PROJECT_ID.iam.gserviceaccount.com \
  --tasks 1 \
  --max-retries 1 \
  --task-timeout 1800s \
  --memory 1Gi \
  --cpu 1 \
  --set-env-vars LOG_LEVEL=INFO,HEADLESS=true \
  --set-secrets EMAIL_FROM=dog-monitor-email-from:latest,EMAIL_TO=dog-monitor-email-to:latest,EMAIL_PASSWORD=dog-monitor-email-password:latest
```

`GOOGLE_CLOUD_PROJECT` is injected automatically by Cloud Run, so
`FIRESTORE_PROJECT_ID` does not need to be set explicitly here.

`--memory 1Gi --cpu 1` are conservative starting points and held up fine in
live testing. The task timeout started at 900s (15 min) per the original
spec but was raised to 1800s (30 min) after a live run against the real
24Petconnect MIAD agency (745 listed animals -- Miami-Dade is a large
county shelter) showed that visiting detail pages for every animal whose
breed text contains "Terrier" as a substring (Pit Bull Terrier, American
Staffordshire Terrier, Boston Terrier, etc. -- intentional, since any of
these *could* individually be a legitimately small dog; see
`matching.classify_breed`) for weight confirmation took longer than 900s
combined with the other three sources. This is a background job on a
4-day cadence, not latency-sensitive, so a longer ceiling is the right
fix rather than reducing scan coverage. Watch actual usage in Cloud
Monitoring after a few real executions and raise `--memory`/`--cpu`
further only if needed (e.g. `gcloud run jobs update dog-monitor-job
--memory 2Gi --cpu 2 --region REGION`).

### 6. Run it once manually to verify

```bash
gcloud run jobs execute dog-monitor-job --region REGION --wait
```

### 7. View logs

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="dog-monitor-job"' \
  --limit 200 --order asc --format='value(textPayload)'
```

or in the Cloud Console: Cloud Run -> Jobs -> dog-monitor-job -> Executions
-> (an execution) -> Logs.

### 8. Schedule it with Cloud Scheduler

Cloud Scheduler invokes the job **once per day** at 08:00 America/New_York;
the application itself enforces the true 96-hour minimum interval between
full scans (see "Architecture" above) by checking
`monitor_state.last_successful_full_scan` in Firestore before scraping, so
most daily invocations simply log "not due yet" and exit 0 immediately.
This is deliberately *not* a `*/4` day-of-month cron expression -- unix-cron
is calendar-based (it resets at month boundaries) and cannot express a true
rolling 4-day interval, so the app enforces it in code instead.

Create an invoker service account and the schedule:

```bash
gcloud iam service-accounts create dog-monitor-scheduler \
  --display-name "Dog Monitor Scheduler Invoker"

gcloud run jobs add-iam-policy-binding dog-monitor-job \
  --region REGION \
  --member="serviceAccount:dog-monitor-scheduler@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

gcloud scheduler jobs create http dog-monitor-schedule \
  --location REGION \
  --schedule "0 8 * * *" \
  --time-zone "America/New_York" \
  --uri "https://REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/dog-monitor-job:run" \
  --http-method POST \
  --oauth-service-account-email dog-monitor-scheduler@PROJECT_ID.iam.gserviceaccount.com
```

Verify and test-fire it:

```bash
gcloud scheduler jobs describe dog-monitor-schedule --location REGION
gcloud scheduler jobs run dog-monitor-schedule --location REGION
```

## Changing the breed rules

All matching logic lives in `dog_monitor/matching.py` and is fully isolated
from scraping/storage/email:

- `EXACT_TERMS`, `STRONG_TERMS`, `POSSIBLE_TERMS`: the phrase lists for each
  confidence tier (case-insensitive substring match).
- `MIN_POSSIBLE_WEIGHT_LB` / `MAX_POSSIBLE_WEIGHT_LB`: the weight window
  (inclusive) a generic "Terrier"/"Terrier Mix"/"Small Terrier" listing must
  fall into to be kept as POSSIBLE when a weight is available.
- `extract_weight()` / `extract_animal_id()`: the weight and animal-ID
  regexes.

After changing anything here, run `pytest tests/test_matching.py -v` --
every rule in the spec (EXACT/STRONG/POSSIBLE cases, weight boundary
behavior, ID extraction) has a dedicated test.

## Adding/adjusting a source

Each scraper implements `BaseScraper.scrape(browser) -> List[Animal]`
(see `scrapers/base.py`) and is registered in `build_scrapers()` in
`main.py`. The two Humane Society scrapers share a generic card-grid engine
(`HumaneSocietyCardScraper`); a new similar WordPress-style source can
usually be added by subclassing it with just a new `url`/`base_url`/
`card_selectors`.

## Troubleshooting

- **"Could not locate any pet card elements..." / "No detail links
  found..."**: the live site's markup differs from the guessed selectors.
  See "IMPORTANT: selectors were not verified against live sites" above.
- **Playwright can't find/launch Chromium**: make sure the `playwright`
  version installed matches the Chromium build actually present (run
  `playwright install chromium` after any `pip install -U playwright`).
  Inside the container this is handled by pinning the Dockerfile's base
  image tag to the same Playwright version as `requirements.txt`.
- **Cloud Run Job runs out of memory**: headless Chromium plus several open
  pages can use significant RAM; raise `--memory` on the job, or reduce
  `DETAIL_PAGE_CONCURRENCY` in `scrapers/petconnect.py`.
- **No email arrives**: check `EMAIL_FROM`/`EMAIL_TO`/`EMAIL_PASSWORD` are
  all set and that `EMAIL_PASSWORD` is a Gmail **App Password** (16
  characters, spaces optional), not the account password. Check the job's
  logs for `Failed to send alert email` (full stack trace is logged).
- **An animal seems to alert twice**: alerts are keyed by `animal_key`
  (`SOURCE_PREFIX:ANIMAL_ID` for 24Petconnect, a SHA-256 fingerprint of
  stable fields for Humane Society listings without an exposed ID) and
  Firestore's `animals.alert_sent` field. If a listing's detail URL or
  description changes in a way that looks "new" you may want to strengthen
  the fingerprint fields used by `build_fingerprint_key()` calls in
  `scrapers/base.py`.
- **One source is always failing**: check `source_runs` in Firestore for
  its latest `error_message` -- the app is designed so a single failing
  source never stops the other three.
