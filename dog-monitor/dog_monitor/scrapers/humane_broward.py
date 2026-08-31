"""Humane Society of Broward County -- all-pets listing scraper."""

from .base import HumaneSocietyCardScraper


class HumaneBrowardScraper(HumaneSocietyCardScraper):
    source_name = "humane_broward"
    region = "Broward"
    url = "https://humanebroward.com/all-pets/?pg=1"
    base_url = "https://humanebroward.com"

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
