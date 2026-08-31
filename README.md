# Dog Monitor

A self-hosted, extensible framework for monitoring animal-shelter adoption
listings for specific breeds, and emailing an alert when a match appears.

## Problem

There is no single reliable database containing every local shelter's
available animals. Someone looking for a particular breed -- a Cairn
Terrier, say -- may have to repeatedly, manually check multiple Humane
Societies, municipal shelters, and third-party adoption platforms, each
with their own site and no shared search. Listings change daily and
nothing notifies you when a match appears.

This project automates that process: it scans a configurable list of
shelter sources on a schedule, classifies each listing against your
target breeds, and emails you when something new matches.

## Quick Start

git clone ...
cd dog-monitor

python -m venv venv
pip install -r requirements.txt
playwright install chromium
pytest
python -m dog_monitor.main

## What It Does

- Scrapes a list of shelter/adoption sources you configure (see
  [`dog_monitor/sources.py`](dog_monitor/sources.py)).
- Classifies each listing's breed text into a confidence tier (see
  "Current Breed Matching" below).
- Deduplicates against previously-seen animals so you're only alerted
  once per new match, using a stable identifier where the source
  provides one, or a deterministic fingerprint where it doesn't.
- Emails a single grouped alert for anything newly matched (or not yet
  successfully alerted) each time it runs.
- Runs as a single, stateless batch job -- no server, no frontend, no
  database to administer beyond the persistence layer it already uses.

## Current Coverage

This is a **reference implementation**. Out of the box it monitors two
Florida counties:

| Source | Region | Platform |
|---|---|---|
| Humane Society of Broward County | Broward County, FL | own site |
| Broward County Animal Care | Broward County, FL | 24Petconnect (agency `BRWD`) |
| Humane Society of Greater Miami | Miami-Dade County, FL | own site |
| Miami-Dade Animal Services | Miami-Dade County, FL | 24Petconnect (agency `MIAD`) |

This list lives entirely in [`dog_monitor/sources.py`](dog_monitor/sources.py) --
see "Adding a Shelter" below for how to extend it to other counties,
states, or countries.

## Current Breed Matching

Breed classification (`dog_monitor/matching.py`) assigns each listing one
of four confidence tiers, from a listing's free-text breed field:

- **EXACT** -- an unambiguous match on a target breed, e.g. "Cairn
  Terrier", "Cairn Terrier Mix", "Norwich Terrier".
- **STRONG** -- a closely related target breed, e.g. "Norfolk Terrier".
- **POSSIBLE** -- a generic label ("Terrier", "Terrier Mix", "Small
  Terrier") that *could* be a target breed, kept only if the listing's
  weight is unknown or falls within a plausible small-terrier range
  (5-30 lb). This deliberately favors false positives over false
  negatives: an unknown-weight generic "Terrier Mix" is kept rather than
  silently dropped, since some sources never publish weight at all.
- **NONE** -- everything else, including a generic "Terrier" label whose
  known weight rules it out (e.g. a 60 lb "Pit Bull Terrier").

The current target breeds are Cairn Terrier, Norwich Terrier, Norfolk
Terrier, and appropriately-sized generic Terrier/Terrier Mix candidates.
These rules -- and the target breed list itself -- are a single,
self-contained, pure-Python module with no scraping/storage/email
dependencies; see its module docstring and `tests/test_matching.py` for
every rule's exact behavior, including the weight-boundary edge cases.

## Architecture

The codebase is organized in three layers, deliberately kept separate so
each can be reasoned about (and replaced) independently:

```
Core application
├── source scrapers    (dog_monitor/scrapers/, dispatched via sources.py)
├── matching           (dog_monitor/matching.py -- pure, no I/O)
├── deduplication       (dog_monitor/database.py's upsert/should_alert logic)
└── alerts              (dog_monitor/alerts.py -- Gmail SMTP)

Persistence
└── Firestore adapter   (dog_monitor/database.py -- the only backend shipped today)

Deployment
├── local Python         (`python -m dog_monitor.main`)
├── Docker                (Dockerfile)
└── Google Cloud reference deployment   (Cloud Run Job + Cloud Scheduler + Secret Manager)
```

One run's data flow, regardless of which deployment layer triggers it:

```
(trigger: Cloud Scheduler, or you running it directly)
    |
    v
Entry point  (`python -m dog_monitor.main`, same code whether local or in a container)
    |
    v
Source adapters / scrapers   ->   Breed matching   ->   Persistence (dedup + alert-sent state)   ->   Email alerts
```

**Google Cloud is not required.** The reference deployment described
below uses Cloud Run, Firestore, Secret Manager, and Cloud Scheduler
because that's what this maintainer's own instance runs on, but the
application itself only depends on a Firestore-compatible persistence
layer -- which includes the local Firestore emulator, requiring no GCP
account at all (see "Local Development"). Nothing about the core
application, scrapers, matching, or alerting logic is GCP-specific. The
persistence layer is accessed through a small, focused interface
(`upsert_animal`, `should_alert`, `mark_alert_sent`, `start_source_run`,
...) — a local SQLite adapter implementing that same interface is a
natural, self-contained first contribution for anyone who wants to run
without Firestore too (see `CONTRIBUTING.md`); none is implemented yet.
Likewise, "Cloud Run Job" is one way to run a container on a schedule --
the Dockerfile and `main.py` don't assume Cloud Run specifically, so
adapting to another container host is mostly a scheduling/secrets
concern, not an application rewrite.

## Project Structure

```
dog_search/
├── dog_monitor/
│   ├── sources.py            # the source registry -- start here to add/edit a shelter
│   ├── config.py             # env-var configuration
│   ├── database.py           # Firestore-backed dedup/alert-state store
│   ├── matching.py           # breed classification + ID/weight extraction (pure, unit-tested)
│   ├── models.py             # Animal / MatchLevel / MatchResult dataclasses
│   ├── alerts.py             # Gmail SMTP email composition + sending
│   ├── logging_config.py     # stdlib logging setup
│   ├── main.py                # orchestration entry point
│   └── scrapers/
│       ├── registry.py            # maps a source's `type` to the right scraper -- start here for a new source type
│       ├── base.py                # BaseScraper interface + generic pet-card engine
│       ├── humane_broward.py      # Humane Society of Broward County adapter
│       ├── humane_miami.py        # Humane Society of Greater Miami adapter
│       └── petconnect.py          # 24Petconnect adapter (any agency code)
├── tests/                     # pytest suite -- see "Testing" below
├── docs/
│   └── DEPLOYMENT.md          # detailed Google Cloud deployment runbook
├── Dockerfile
├── requirements.txt
├── cloudbuild.yaml            # Cloud Build pipeline: test -> build -> push -> deploy
├── .env.example
├── LICENSE
├── CONTRIBUTING.md
└── README.md
```

## Adding a Shelter

Source metadata is centralized in `dog_monitor/sources.py` specifically
so that **adding a shelter should not require touching `main.py`**.
Orchestration just iterates `sources.enabled_sources()` and dispatches
each entry through `scrapers/registry.py` -- neither of those needs to
change for a source that fits an existing type.

**If the new shelter uses a platform already supported** (currently
24Petconnect, or a WordPress/CMS-style "pet card" grid like the two
Humane Society sites), adding it is a `sources.py` edit:

```python
SourceConfig(
    id="humane-yourcity",
    name="Humane Society of Your City",
    region="Your County, ST",
    type="humane",
    url="https://example.org/adopt/",
    parser="humane_yourcity",   # a new HumaneSocietyCardScraper subclass, see below
),
```

For a `"humane"`-type source you'll typically also add a small adapter
(most of the parsing logic is shared):

```python
# dog_monitor/scrapers/humane_yourcity.py
from .base import HumaneSocietyCardScraper

class HumaneYourCityScraper(HumaneSocietyCardScraper):
    source_name = "humane_yourcity"   # stable Firestore/dedup key -- see below
    card_selectors = [".pet-card", ...]  # verified against the live site
```

...then register it in `scrapers/registry.py`'s `_HUMANE_PARSERS` dict.
A `"24petconnect"`-type source needs no new code at all -- just an
`agency_code` in its `sources.py` entry.

**If the new shelter needs a genuinely new scraping strategy** (a
different platform, e.g. Petfinder or ShelterLuv), implement a new
`BaseScraper` subclass and add one factory function + one entry to
`SCRAPER_REGISTRY` in `scrapers/registry.py`. That's the only file that
maps a source `type` string to actual scraper construction, so a future
`type: "petfinder"` or `type: "shelterluv"` doesn't require rewriting
orchestration.

One important stability note: each scraper's `source_name` (e.g.
`"humane_broward"`) is written into Firestore and folded into dedup
fingerprint keys for sources without a native animal ID -- pick it once
and don't change it after real data exists. See `CONTRIBUTING.md`'s
"Adding a New Shelter" section for the full contribution checklist,
including tests.

## Configuration

All configuration is environment variables (see `.env.example` for the
full list with no real values):

| Variable | Required | Purpose |
|---|---|---|
| `EMAIL_FROM` | for alerts | Gmail address alerts are sent from |
| `EMAIL_TO` | for alerts | address alerts are sent to |
| `EMAIL_PASSWORD` | for alerts | a Gmail **App Password**, not your account password |
| `HEADLESS` | no (default `true`) | run Chromium headless; set `false` to watch it locally |
| `LOG_LEVEL` | no (default `INFO`) | stdlib logging level |
| `FIRESTORE_PROJECT_ID` | no | usually auto-detected from `GOOGLE_CLOUD_PROJECT` in Cloud Run |
| `FIRESTORE_DATABASE_ID` | no | only needed for a named (non-default) Firestore database |
| `FIRESTORE_EMULATOR_HOST` | no | point at a local Firestore emulator instead of real GCP |

Missing email configuration is not fatal -- a scan still runs and stores
matches in Firestore; alerting is just skipped (with a logged warning)
until it's configured, and pending matches are retried on the next run.

## Local Development

```bash
python3 -m venv venv
source venv/bin/activate       # venv\Scripts\activate on Windows
pip install -r requirements.txt
playwright install chromium
cp .env.example .env           # fill in your own values; this file is gitignored
pytest                         # no GCP account needed -- see "Testing" below
python -m dog_monitor.main     # one full scan against real sources
```

Set `HEADLESS=false` in `.env` to watch the browser while debugging a
scraper. To exercise the app against real Firestore semantics without a
real GCP project, run the Firestore emulator:

```bash
gcloud emulators firestore start --host-port=localhost:8080
# in another terminal:
export FIRESTORE_EMULATOR_HOST=localhost:8080
export FIRESTORE_PROJECT_ID=demo-test   # any non-empty value works against the emulator
python -m dog_monitor.main
```

## Google Cloud Deployment

The reference deployment target is a Cloud Run Job, triggered daily by
Cloud Scheduler, using Firestore for persistence, Secret Manager for
email credentials, and Cloud Build to test/build/push/deploy the
container. This is one deployment option, not a requirement -- the
application only needs Firestore (or the emulator) and a place to run a
container to completion on a schedule.

See **[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)** for the full,
copy-pasteable setup: enabling APIs, creating the Firestore database and
Artifact Registry repo, IAM, secrets, creating the job, and scheduling
it.

## Testing

```bash
pytest
```

No GCP account or network access is required: matching/extraction logic
is pure Python, Firestore interactions run against an in-memory fake
client (`tests/fakes.py`), and scraper parsing tests exercise real
field-extraction logic against literal text samples captured from the
live sites -- rather than requiring a live browser session in CI.

If `pytest-cov` is installed:

```bash
pytest --cov
```

The suite covers source-registry validation, breed matching, weight/ID
extraction, scraper parsing (Humane Society card fields, 24Petconnect
list/pagination/detail parsing), Firestore-backed deduplication and
alert-retry state, the 96-hour scan guard, and orchestration behavior
(source failure isolation, disabled-source skipping). It does not cover
live-browser/network behavior -- parsing tests run against literal text
samples captured from the real sites rather than a live Playwright
session, so a scraper can still break if a site's markup changes even
though its tests keep passing; see "Responsible Scraping" above.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full process, including
the preferred way to add a new shelter.

## Responsible Scraping

- Respect each source site's terms of use. This project doesn't ship
  with permission from any shelter or platform to scrape it -- that's
  each operator's responsibility to confirm for their own use.
- Use conservative request rates. Scrapers here deliberately pace
  requests (see `PAGE_LOAD_DELAY_SECONDS`, `DETAIL_PAGE_DELAY_SECONDS` in
  `scrapers/petconnect.py`) and only visit a listing's detail page when
  it's already a breed match, not for every listing scanned.
- Do not aggressively crawl sites. This is a periodic monitor (every few
  days), not a real-time crawler -- don't reduce the scan interval or
  strip pacing to get fresher data faster.
- Individual source implementations may break when a site's markup
  changes; that's expected maintenance, not a design flaw. Each scraper
  fails independently (see "Source failure isolation" below) and logs a
  clear warning rather than silently returning wrong data.
- Contributors are responsible for ensuring their own source
  implementations comply with the target site's terms and any applicable
  legal requirements in their jurisdiction.

## Non-Goals

This project explicitly does **not** intend to:

- Operate a nationwide hosted service. There is no hosted public
  instance; you fork or clone and run your own.
- Provide a polished consumer frontend. It's a backend job that emails
  you -- there is no UI, and none is planned in the base repository.
- Guarantee permanent compatibility with third-party websites. Shelter
  sites change their markup without notice; scrapers will need ongoing
  maintenance.
- Guarantee breed identification accuracy. Matching is based on
  shelter-provided text and weight, which is often approximate,
  inconsistent, or (for some sources) simply missing.
- Replace official shelter records. Always confirm availability directly
  with the shelter before making plans.

## License

MIT -- see [`LICENSE`](LICENSE). Forks and derivative projects,
including commercial ones, are explicitly permitted. The maintainer(s)
are not committing to operate any hosted service, nationwide or
otherwise, on your behalf.
