# Contributing

Thanks for considering a contribution. This project is a self-hosted
reference implementation, not a hosted service -- most contributions are
either a new shelter/source, a fix to an existing scraper (sites change
their markup), or an improvement to matching/alerting/persistence.

## Contribution process

1. Fork the repository.
2. Create a feature branch off `main`.
3. Add or modify a source/scraper (see "Adding a New Shelter" below).
4. Add tests covering the new or changed behavior.
5. Run `pytest` and confirm the full suite passes.
6. Commit your changes with a clear, descriptive message.
7. Open a pull request describing what changed and why.

## Guidelines

- **Never commit credentials.** No passwords, Gmail App Passwords, API
  keys, OAuth client secrets, or service-account JSON files. If you're
  unsure whether something is sensitive, leave it out and ask.
- **Never commit `.env`.** Use `.env.example` (with empty/placeholder
  values) to document what a new source or feature needs; real values
  stay in your own local `.env` or your deployment's secret store.
- **Keep scraper request frequency conservative.** Don't tighten delays,
  raise concurrency, or remove pacing/backoff to make a scraper "faster."
  These are shared, real third-party sites -- scrape politely.
- **Add tests for new parsing behavior.** A scraper change without a
  test that would have caught the bug isn't done. Prefer testing pure
  parsing functions (regexes, field extraction, classification) directly
  over trying to mock a full browser session.
- **Avoid changing unrelated code.** Keep pull requests focused on one
  source, one bug, or one feature at a time.
- **Document new source IDs and agency codes.** If you add a source,
  give it a clear `id` in `sources.py` and mention its agency
  code/platform in your PR description.
- **Use stable animal IDs whenever available.** Dedup and alerting
  depend on a stable `animal_key` (see "Adding a New Shelter" below) --
  prefer a real shelter/platform ID over a fingerprint whenever the
  source exposes one.

## Adding a New Shelter

Most new shelters need **zero changes to orchestration code**
(`main.py`). The process is:

1. **Check if an existing source type already fits.** If the new
   shelter publishes through 24Petconnect, you likely just need a new
   entry in `dog_monitor/sources.py` with `type="24petconnect"` and the
   right `agency_code` -- no new scraper code at all. If it's a
   WordPress/CMS-style "pet card" grid site similar to the two current
   Humane Society sources, you may only need a new thin subclass of
   `HumaneSocietyCardScraper` (see `dog_monitor/scrapers/humane_broward.py`
   for the minimal shape: a `source_name` and a `card_selectors` list).

2. **If the site genuinely needs new scraping logic** (a different
   platform, e.g. Petfinder or ShelterLuv), implement a new
   `BaseScraper` subclass in `dog_monitor/scrapers/`, following the
   pattern in `scrapers/petconnect.py`: raise `ScraperError` if the
   source's workflow can't complete at all (so one broken source doesn't
   take down the whole run), and return an `Animal` per listing found
   (matched or not -- the caller filters by `match_level`).

3. **Register the new type in `dog_monitor/scrapers/registry.py`**: add
   one `_build_*` factory function and one entry in `SCRAPER_REGISTRY`.
   This is the only place that maps a source `type` string to actual
   scraper construction.

4. **Add the source to `dog_monitor/sources.py`**: a new `SourceConfig`
   entry with `id`, `name`, `region`, `type`, and whatever fields that
   type needs (`url`/`parser` for `"humane"`, `agency_code` for
   `"24petconnect"`). This is a plain data edit -- no imports, no
   orchestration logic.

5. **Pick a stable, permanent `source_name`** for your scraper class
   (e.g. `"humane_yourcity"`). This becomes the Firestore `source` field
   and, for sources without a native ID, is folded into the dedup
   fingerprint key -- so once real data exists, don't change it.

6. **Write tests.** At minimum: parsing tests for any new field-extraction
   regex/logic against a real (or realistically-shaped) sample of the
   site's text, plus confirming your new source appears in
   `sources.enabled_sources()` and dispatches to the right scraper class
   via `scrapers.registry.build_scraper()`. See `tests/test_sources.py`
   and `tests/test_petconnect_parsing.py` for examples.

7. **Verify against the live site once, manually**, before opening a PR
   -- shelter-site markup can't be verified from within a sandboxed CI
   environment. Note in your PR description what you checked (e.g.
   "confirmed card selector and field extraction against N live
   listings on <date>").

If you want to *disable* a source rather than remove it (e.g. it's
temporarily broken), set `enabled=False` in its `sources.py` entry --
orchestration skips disabled sources automatically.

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
playwright install chromium
cp .env.example .env       # fill in your own local values, never commit this file
pytest
```

See `README.md`'s "Local Development" section for more detail, including
running against the Firestore emulator.
