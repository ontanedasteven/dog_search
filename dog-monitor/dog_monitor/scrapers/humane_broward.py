"""Humane Society of Broward County -- all-pets listing scraper."""

from .base import HumaneSocietyCardScraper


class HumaneBrowardScraper(HumaneSocietyCardScraper):
    source_name = "humane_broward"
    region = "Broward"
    url = "https://humanebroward.com/all-pets/?pg=1"
    base_url = "https://humanebroward.com"

    # See base.py's module docstring: verify these against the live DOM on
    # first deployment and update if the site logs a selector warning.
    card_selectors = [
        ".pet-card",
        ".animal-card",
        "[class*='pet-item']",
        "[class*='petCard']",
        "li.pet",
        ".grid-item.pet",
        "article.pet",
        "[class*='pet-listing']",
    ]
