"""Humane Society of Greater Miami -- adopt-a-pet listing scraper.

`url` and `region` are supplied by the caller (see sources.py's
"humane-miami" entry and scrapers/registry.py) rather than hardcoded
here, so this class only needs to carry markup knowledge specific to this
site's card grid.
"""

from .base import HumaneSocietyCardScraper


class HumaneMiamiScraper(HumaneSocietyCardScraper):
    # Stable Firestore/dedup identity for this source. Existing
    # `animals`/`sightings`/`source_runs` documents are keyed off this
    # exact string -- do not change it without a data migration.
    source_name = "humane_miami"

    # Verified live on 2026-08-31: cards are `<li class="adoptable-pet-card
    # visible">` (server-rendered, no JS wait needed). Kept as the first
    # candidate; the rest remain as fallbacks in case the site's markup
    # changes again.
    card_selectors = [
        ".adoptable-pet-card",
        ".pet-item",
        ".pet-card",
        "[class*='animal-card']",
        "[class*='petItem']",
        ".grid-item",
        "article.pet",
        "[class*='pet-listing']",
    ]
