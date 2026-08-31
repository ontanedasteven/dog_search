"""Humane Society of Broward County -- all-pets listing scraper.

`url` and `region` are supplied by the caller (see sources.py's
"humane-broward" entry and scrapers/registry.py) rather than hardcoded
here, so this class only needs to carry markup knowledge specific to this
site's card grid.
"""

from .base import HumaneSocietyCardScraper


class HumaneBrowardScraper(HumaneSocietyCardScraper):
    # Stable Firestore/dedup identity for this source. Existing
    # `animals`/`sightings`/`source_runs` documents are keyed off this
    # exact string -- do not change it without a data migration.
    source_name = "humane_broward"

    # Verified live on 2026-08-31: cards are `<div class="pet-item">`
    # containing a nested `<a class="pet-item-link">`. The nested anchor's
    # class also contains the substring "pet-item", so a wildcard
    # `[class*='pet-item']` selector matches BOTH the card and its own
    # child, double-counting every animal. `div.pet-item` is exact and
    # tag-scoped so it only matches the card itself. Kept as the first
    # candidate; the rest remain fallbacks in case markup changes again.
    card_selectors = [
        "div.pet-item",
        ".pet-card",
        ".animal-card",
        "[class*='petCard']",
        "li.pet",
        ".grid-item.pet",
        "article.pet",
        "[class*='pet-listing']",
    ]
