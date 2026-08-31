"""Dispatches a `SourceConfig` (see `dog_monitor.sources`) to the scraper
that knows how to scrape it.

This exists so orchestration never has to grow a chain of
`if source.type == "humane": ... elif source.type == "24petconnect": ...`.
Adding a new source *type* (e.g. "petfinder" or "shelterluv") means
writing one new `_build_*` factory and adding one line to
`SCRAPER_REGISTRY` -- `main.py` and `sources.py` do not change.
"""

from typing import Callable, Dict

from ..sources import SourceConfig
from .base import BaseScraper
from .humane_broward import HumaneBrowardScraper
from .humane_miami import HumaneMiamiScraper
from .petconnect import PetConnectScraper

ScraperFactory = Callable[[SourceConfig, bool], BaseScraper]

# "humane"-type sources share a common scraping engine
# (HumaneSocietyCardScraper) but each site's card markup differs, so each
# gets its own thin subclass carrying just `card_selectors`. A source's
# `parser` field picks which one. (See sources.py's module docstring for
# why this is a separate concept from a source's stable Firestore
# `source_name`.)
_HUMANE_PARSERS: Dict[str, type] = {
    "humane_broward": HumaneBrowardScraper,
    "humane_miami": HumaneMiamiScraper,
}


def _build_humane(source: SourceConfig, headless: bool) -> BaseScraper:
    if not source.url:
        raise ValueError(f"humane-type source {source.id!r} is missing url")
    parser_cls = _HUMANE_PARSERS.get(source.parser or "")
    if parser_cls is None:
        raise ValueError(
            f"Unknown parser {source.parser!r} for humane-type source {source.id!r}. "
            f"Known parsers: {sorted(_HUMANE_PARSERS)}. Add a new HumaneSocietyCardScraper "
            "subclass and register it in _HUMANE_PARSERS if this is a genuinely new site."
        )
    return parser_cls(url=source.url, region=source.region, headless=headless)


def _build_24petconnect(source: SourceConfig, headless: bool) -> BaseScraper:
    if not source.agency_code:
        raise ValueError(f"24petconnect-type source {source.id!r} is missing agency_code")
    return PetConnectScraper(agency_code=source.agency_code, region=source.region, headless=headless)


# Add an entry here (and a `_build_*` factory above) to support a new
# source type without touching main.py or sources.py.
SCRAPER_REGISTRY: Dict[str, ScraperFactory] = {
    "humane": _build_humane,
    "24petconnect": _build_24petconnect,
}


def build_scraper(source: SourceConfig, headless: bool) -> BaseScraper:
    """Build the BaseScraper instance for one enabled source. Raises
    ValueError for an unregistered type or missing required field, so a
    typo in sources.py fails loudly at startup instead of silently
    skipping a source."""
    factory = SCRAPER_REGISTRY.get(source.type)
    if factory is None:
        raise ValueError(
            f"No scraper registered for source type {source.type!r} (source {source.id!r}). "
            f"Known types: {sorted(SCRAPER_REGISTRY)}"
        )
    return factory(source, headless)
