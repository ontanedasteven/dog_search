# Deploying to Google Cloud

This is the detailed, copy-pasteable runbook for deploying your own
instance to Google Cloud Run. `README.md`'s "Google Cloud Deployment"
section gives the high-level picture; this document is the step-by-step
version. It assumes you're setting up your **own** GCP project -- there is
no shared/hosted deployment.

Replace `PROJECT_ID` and `REGION` (e.g. `us-east1`) throughout.

## 1. One-time project setup

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

## 2. Store the email credentials as secrets

```bash
printf '%s' 'you@gmail.com'        | gcloud secrets create dog-monitor-email-from     --data-file=-
printf '%s' 'you@gmail.com'        | gcloud secrets create dog-monitor-email-to       --data-file=-
printf '%s' 'xxxxxxxxxxxxxxxx'     | gcloud secrets create dog-monitor-email-password --data-file=-
```

`EMAIL_PASSWORD` must be a Gmail **App Password**, not your normal
account password (Gmail rejects normal passwords for SMTP from
third-party apps):

1. Enable 2-Step Verification: https://myaccount.google.com/security
2. Create an app password: https://myaccount.google.com/apppasswords
   (choose "Mail" / "Other"), copy the 16-character value.

## 3. Create a dedicated service account for the job

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

Grant only what's required -- no `Owner`/`Editor` role, no broader
Firestore/Secret Manager access than the above.

## 4. Build and push the image

```bash
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT_ID/dog-monitor-repo/dog-monitor:latest
```

## 5. Create the Cloud Run Job

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

`--memory 1Gi --cpu 1` are conservative starting points. The 1800s (30
min) task timeout accounts for larger county shelters: 24Petconnect
detail-page enrichment only runs for animals whose breed text already
matches (see `matching.classify_breed`), but a large agency can still
have hundreds of "___ Terrier"-labelled listings worth checking. Watch
actual usage in Cloud Monitoring after a few real executions and adjust
`--memory`/`--cpu`/`--task-timeout` if needed, e.g.:

```bash
gcloud run jobs update dog-monitor-job --memory 2Gi --cpu 2 --region REGION
```

## 6. Run it once manually to verify

```bash
gcloud run jobs execute dog-monitor-job --region REGION --wait
```

## 7. View logs

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="dog-monitor-job"' \
  --limit 200 --order asc --format='value(textPayload)'
```

or in the Cloud Console: Cloud Run -> Jobs -> dog-monitor-job -> Executions
-> (an execution) -> Logs.

## 8. Schedule it with Cloud Scheduler

Cloud Scheduler invokes the job **once per day**; the application itself
enforces the true 96-hour minimum interval between full scans (see
`main.is_scan_due`), so most daily invocations just log "not due yet" and
exit 0 immediately. This is deliberate -- unix-cron is calendar-based (a
`*/4` day-of-month expression resets at month boundaries) and cannot
express a true rolling 4-day interval, so the app enforces it in code
instead of relying on the scheduler's cadence.

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

## Auto-deploy on push (optional)

`cloudbuild.yaml` runs the unit test suite (aborting the whole build if
any test fails), then builds the image, pushes it to Artifact Registry
tagged with both `$SHORT_SHA` and `latest`, and updates the
already-created Cloud Run Job to use the `$SHORT_SHA`-tagged image. To
wire this to fire automatically on push, connect your GitHub repository
to Cloud Build (Console -> Cloud Build -> Triggers -> Connect Repository
-- this step requires interactive GitHub OAuth authorization and can't be
scripted) and create a trigger pointing at `cloudbuild.yaml`.

To run it manually instead:

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION=REGION,_REPO=dog-monitor-repo,_IMAGE_NAME=dog-monitor,_JOB_NAME=dog-monitor-job
```

The build service account needs `roles/artifactregistry.writer` and
`roles/run.developer` in addition to its default permissions for the
build/push/deploy steps to succeed.

## Containerizing locally

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

(Mounting `~/.config/gcloud` lets the container use your local `gcloud
auth application-default login` credentials for a local Docker smoke test
against real Firestore. In Cloud Run itself, credentials come from the
job's attached service account automatically -- no mounting needed.)

The `Dockerfile`'s base image tag must match the `playwright` version
pinned in `requirements.txt` so the bundled Chromium build lines up -- if
you bump one, bump the other.

## Troubleshooting

- **"Could not locate any pet card elements..." / "No animal cards
  found..."**: the live site's markup changed since a scraper's
  `card_selectors` were last verified. Open the page in a real browser,
  inspect the DOM (devtools), and update the relevant `scrapers/*.py`
  module. Each `HumaneSocietyCardScraper` subclass documents the date its
  selectors were last verified live.
- **Playwright can't find/launch Chromium**: make sure the `playwright`
  version installed matches the Chromium build actually present (run
  `playwright install chromium` after any `pip install -U playwright`).
  Inside the container this is handled by pinning the Dockerfile's base
  image tag to the same Playwright version as `requirements.txt`.
- **Cloud Run Job runs out of memory or times out**: headless Chromium
  plus many open pages can use significant RAM/time, especially for a
  large county shelter's 24Petconnect feed; raise `--memory`, `--cpu`,
  or `--task-timeout` on the job.
- **No email arrives**: check `EMAIL_FROM`/`EMAIL_TO`/`EMAIL_PASSWORD`
  are all set and that `EMAIL_PASSWORD` is a Gmail **App Password** (16
  characters), not the account password. Check the job's logs for
  `Failed to send alert email` (a full SMTP stack trace is logged, and
  the affected animals stay `alert_sent=False` in Firestore for retry on
  the next scan -- see "Failed email retry behavior" in `dog_monitor/main.py`).
- **An animal seems to alert twice**: alerts are keyed by `animal_key`
  (`AGENCY:ANIMAL_ID` for 24Petconnect, a SHA-256 fingerprint of stable
  fields for Humane Society listings without an exposed ID) and
  Firestore's `animals.alert_sent` field. If a listing's detail URL or
  description changes in a way that looks "new," you may want to
  strengthen the fingerprint fields used by `build_fingerprint_key()`
  calls in `scrapers/base.py`.
- **One source is always failing**: check `source_runs` in Firestore for
  its latest `error_message` -- the app is designed so a single failing
  source never stops the others (see "Source failure isolation" in
  `dog_monitor/main.py`).
