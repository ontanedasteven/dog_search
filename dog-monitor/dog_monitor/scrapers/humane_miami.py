"""Humane Society of Greater Miami -- adopt-a-pet listing scraper."""

from .base import HumaneSocietyCardScraper


class HumaneMiamiScraper(HumaneSocietyCardScraper):
    source_name = "humane_miami"
    region = "Miami-Dade"
    url = "https://www.humanesocietymiami.org/adopt-a-pet-today/"
    base_url = "https://www.humanesocietymiami.org"

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
