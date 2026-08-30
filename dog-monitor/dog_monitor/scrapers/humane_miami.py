"""Humane Society of Greater Miami -- adopt-a-pet listing scraper."""

from .base import HumaneSocietyCardScraper


class HumaneMiamiScraper(HumaneSocietyCardScraper):
    source_name = "humane_miami"
    region = "Miami-Dade"
    url = "https://www.humanesocietymiami.org/adopt-a-pet-today/"
    base_url = "https://www.humanesocietymiami.org"

    # See base.py's module docstring: verify these against the live DOM on
    # first deployment and update if the site logs a selector warning.
    card_selectors = [
        ".pet-item",
        ".pet-card",
        "[class*='animal-card']",
        "[class*='petItem']",
        ".grid-item",
        "article.pet",
        "[class*='pet-listing']",
    ]
