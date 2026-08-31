"""Orchestration entry point.

Running `python -m dog_monitor.main` performs one complete scan of all four
sources, stores/dedups matches in Firestore, and sends a single grouped
email for any newly matched (or previously unalerted) animals. The process
is stateless between executions -- all dedup/alert state lives in Firestore,
which is exactly what Cloud Run Jobs expects (each execution is a fresh
container).

Cloud Scheduler may invoke this job as often as once per day, but a full
shelter scan should only actually happen once every 96 hours (four days).
That interval is enforced here, not in the scheduler: `is_scan_due()` reads
`monitor_state.last_successful_full_scan` from Firestore before touching
Playwright or any scraper, and exits successfully (without scraping) if
fewer than 96 hours have elapsed. This is a true rolling interval, not a
calendar-based cron approximation (e.g. `*/4` in the day-of-month field
resets at each month boundary and is not equivalent to "every 96 hours").

Exit codes:
  0 - the run completed (scan performed, or skipped because it wasn't due
      yet), even if one or more individual sources failed.
  1 - a fatal application-level error (invalid configuration, or the
      Firestore client could not be initialized).
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import List

from playwright.sync_api import sync_playwright

from .alerts import send_alert_email
from .config import Config, ConfigError, load_config
from .database import FirestoreStore
from .logging_config import configure_logging
from .models import Animal, MatchLevel
from .scrapers.base import BaseScraper, ScraperError
from .scrapers.humane_broward import HumaneBrowardScraper
from .scrapers.humane_miami import HumaneMiamiScraper
from .scrapers.petconnect import PetConnectScraper

logger = logging.getLogger(__name__)

# Minimum time between full shelter scans. Cloud Scheduler may trigger this
# job daily; is_scan_due() gates the actual scraping on this true rolling
# window rather than relying on the scheduler's cadence.
FULL_SCAN_INTERVAL_HOURS = 96


def build_scrapers(headless: bool) -> List[BaseScraper]:
    return [
        HumaneBrowardScraper(headless=headless),
        HumaneMiamiScraper(headless=headless),
        PetConnectScraper(agency_code="BRWD", region="Broward", headless=headless),
        PetConnectScraper(agency_code="MIAD", region="Miami-Dade", headless=headless),
    ]


def run_source(db: FirestoreStore, browser, scraper: BaseScraper) -> List[Animal]:
    """Run a single scraper. Never raises -- failures are logged and
    recorded in source_runs so the rest of the sources still run."""
    run_id = db.start_source_run(scraper.source_name)
    logger.info("Starting source: %s", scraper.source_name)
    try:
        animals = scraper.scrape(browser)
        matches = [a for a in animals if a.match_level != MatchLevel.NONE]
        db.finish_source_run(
            run_id, success=True, animals_scanned=len(animals), matches_found=len(matches)
        )
        logger.info(
            "Completed source %s: animals_scanned=%d matches_found=%d",
            scraper.source_name, len(animals), len(matches),
        )
        return matches
    except ScraperError as exc:
        logger.error("Source %s failed: %s", scraper.source_name, exc)
        db.finish_source_run(run_id, success=False, error_message=str(exc))
        return []
    except Exception as exc:
        logger.exception("Unexpected error in source %s", scraper.source_name)
        db.finish_source_run(run_id, success=False, error_message=str(exc))
        return []


def process_matches(db: FirestoreStore, matches: List[Animal]) -> List[Animal]:
    """Upsert/dedup matches for one source. Returns the subset that still
    need an alert sent (new animals, plus any animal whose previous alert
    attempt failed)."""
    alertable: List[Animal] = []
    new_count = 0
    duplicate_count = 0

    for animal in matches:
        is_new = db.upsert_animal(animal)
        if is_new:
            new_count += 1
            logger.info(
                "New match: %s (%s) [%s: %s]",
                animal.name, animal.animal_key, animal.match_level.value, animal.matched_term,
            )
        else:
            duplicate_count += 1

        if db.should_alert(animal.animal_key):
            alertable.append(animal)

    logger.info(
        "Source summary: new=%d duplicate=%d pending_alert=%d",
        new_count, duplicate_count, len(alertable),
    )
    return alertable


def send_pending_alerts(db: FirestoreStore, config: Config, alertable: List[Animal]) -> None:
    if not alertable:
        logger.info("No new matches requiring alerts this run.")
        return

    logger.info("Sending alert email for %d animal(s) pending alert.", len(alertable))
    if not config.email_configured:
        logger.warning(
            "EMAIL_FROM/EMAIL_TO/EMAIL_PASSWORD not fully configured; skipping "
            "send. These %d animal(s) remain pending and will be retried next run.",
            len(alertable),
        )
        return

    sent = send_alert_email(config, alertable)
    if sent:
        for animal in alertable:
            db.mark_alert_sent(animal.animal_key)
        logger.info("Alert email delivered; marked %d animal(s) as alerted.", len(alertable))
    else:
        logger.error(
            "Alert email failed to send; %d animal(s) left unalerted for retry next run.",
            len(alertable),
        )


def is_scan_due(db: FirestoreStore, interval_hours: float = FULL_SCAN_INTERVAL_HOURS) -> bool:
    """True if a full scan has never completed, or the last one completed
    at least `interval_hours` ago."""
    last = db.get_last_successful_full_scan()
    if last is None:
        return True
    elapsed = datetime.now(timezone.utc) - last
    return elapsed >= timedelta(hours=interval_hours)


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Fatal configuration error: {exc}", file=sys.stderr)
        return 1

    configure_logging(level=config.log_level)
    logger.info("=== Dog monitor run starting ===")

    try:
        db = FirestoreStore(project=config.firestore_project, database=config.firestore_database)
    except Exception:
        logger.exception("Fatal error initializing Firestore client")
        return 1

    try:
        if not is_scan_due(db):
            last = db.get_last_successful_full_scan()
            logger.info(
                "Full scan not due yet (last_successful_full_scan=%s, "
                "interval=%dh); skipping scrape for this invocation.",
                last.isoformat() if last else None, FULL_SCAN_INTERVAL_HOURS,
            )
            return 0

        all_alertable: List[Animal] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=config.headless)
            try:
                for scraper in build_scrapers(config.headless):
                    matches = run_source(db, browser, scraper)
                    all_alertable.extend(process_matches(db, matches))
            finally:
                browser.close()

        send_pending_alerts(db, config, all_alertable)
        db.update_last_successful_full_scan()
        logger.info("Recorded last_successful_full_scan for this run.")
    finally:
        db.close()

    logger.info("=== Dog monitor run finished ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
