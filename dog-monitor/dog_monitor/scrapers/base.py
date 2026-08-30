"""Shared scraper infrastructure: the BaseScraper interface plus a generic
engine for card-grid pet listing pages, reused by both Humane Society
scrapers.

IMPORTANT SELECTOR CAVEAT: the CSS selectors used by HumaneSocietyCardScraper
subclasses are best-effort guesses at common shelter-site markup patterns.
This project was built in a sandboxed environment with no outbound network
access to the live shelter sites, so the selectors were NOT verified against
the real rendered DOM. On first real deployment, watch the logs for
"Could not locate any pet card elements" warnings -- that means the live
markup differs and the `card_selectors` list in the relevant scraper module
needs to be updated after inspecting the real page (e.g. via browser
devtools). The engine is written so that updating selectors is the only
change needed; the parsing/extraction logic below is markup-agnostic.
"""

import logging
import re
from abc import ABC, abstractmethod
from typing import List, Optional
from urllib.parse import urljoin

from playwright.sync_api import Browser, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from ..matching import build_fingerprint_key, classify_breed, extract_animal_id, extract_weight
from ..models import Animal

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Raised when a scraper cannot complete its workflow. The caller records
    this as a failed source_runs entry and continues with the remaining
    sources rather than aborting the whole application."""


class BaseScraper(ABC):
    source_name: str = "unknown"
    region: str = "unknown"

    def __init__(self, headless: bool = True, timeout_ms: int = 30000):
        self.headless = headless
        self.timeout_ms = timeout_ms

    @abstractmethod
    def scrape(self, browser: Browser) -> List[Animal]:
        """Return every animal found on the source (matched or not -- the
        caller filters by match_level). Raise ScraperError if the source's
        workflow cannot be completed at all."""
        raise NotImplementedError


_LOAD_MORE_RE = re.compile(r"load\s*more|show\s*more", re.IGNORECASE)
MAX_SCROLL_ITERATIONS = 15
MAX_LOAD_MORE_CLICKS = 15


class HumaneSocietyCardScraper(BaseScraper):
    """Generic engine for WordPress/CMS-style "pet card" listing pages.

    Subclasses set `url`, `base_url`, and `card_selectors`; this class
    handles page load, lazy-load scrolling, "Load More" buttons, card
    discovery, and field extraction.
    """

    url: str = ""
    base_url: str = ""
    card_selectors: List[str] = []

    def scrape(self, browser: Browser) -> List[Animal]:
        page = browser.new_page()
        try:
            page.set_default_timeout(self.timeout_ms)
            logger.info("[%s] Loading %s", self.source_name, self.url)
            page.goto(self.url, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            self._expand_listing(page)

            selector, cards = self._find_cards(page)
            if not selector:
                raise ScraperError(
                    f"[{self.source_name}] Could not locate any pet card elements "
                    f"using known selectors {self.card_selectors}. The site markup "
                    "may have changed and selectors in this scraper module need updating."
                )

            logger.info(
                "[%s] Found %d cards using selector '%s'", self.source_name, len(cards), selector
            )

            animals: List[Animal] = []
            for card in cards:
                animal = self._parse_card(card)
                if animal is not None:
                    animals.append(animal)
            return animals
        finally:
            page.close()

    def _expand_listing(self, page: Page) -> None:
        last_height = 0
        for _ in range(MAX_SCROLL_ITERATIONS):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(500)
            try:
                height = page.evaluate("document.body.scrollHeight")
            except Exception:
                break
            if height == last_height:
                break
            last_height = height

        for _ in range(MAX_LOAD_MORE_CLICKS):
            try:
                button = page.get_by_text(_LOAD_MORE_RE)
                if button.count() == 0:
                    break
                button.first.scroll_into_view_if_needed(timeout=2000)
                button.first.click(timeout=3000)
                page.wait_for_timeout(1500)
            except PlaywrightTimeoutError:
                break
            except Exception:
                break

    def _find_cards(self, page: Page):
        for selector in self.card_selectors:
            try:
                elements = page.query_selector_all(selector)
            except Exception:
                logger.warning(
                    "[%s] Selector '%s' raised an error; trying next candidate.",
                    self.source_name, selector, exc_info=True,
                )
                continue
            if elements:
                return selector, elements
        return None, []

    def _parse_card(self, card) -> Optional[Animal]:
        try:
            text = (card.inner_text() or "").strip()
        except Exception:
            return None
        if not text:
            return None

        link_el = card.query_selector("a")
        href = link_el.get_attribute("href") if link_el else None
        detail_url = urljoin(self.base_url or self.url, href) if href else self.url

        img_el = card.query_selector("img")
        raw_image = img_el.get_attribute("src") if img_el else None
        image_url = urljoin(self.base_url or self.url, raw_image) if raw_image else None

        name = None
        name_el = card.query_selector("h2, h3, h4, .pet-name, .name, .card-title")
        if name_el:
            try:
                name = (name_el.inner_text() or "").strip() or None
            except Exception:
                name = None
        if not name:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            name = lines[0] if lines else None

        breed_text = text
        weight = extract_weight(text)
        animal_id = extract_animal_id(text)
        age = self._extract_labelled(text, ["age"])
        sex = self._extract_labelled(text, ["sex", "gender"])

        match = classify_breed(breed_text, weight=weight)

        animal_key = (
            f"{self.source_name}:{animal_id}"
            if animal_id
            else build_fingerprint_key(self.source_name, name, breed_text, detail_url)
        )

        return Animal(
            animal_key=animal_key,
            source=self.source_name,
            region=self.region,
            url=detail_url,
            animal_id=animal_id,
            name=name,
            breed_text=breed_text,
            description=text[:2000],
            age=age,
            sex=sex,
            weight=match.weight,
            image_url=image_url,
            match_level=match.level,
            matched_term=match.matched_term,
        )

    @staticmethod
    def _extract_labelled(text: str, labels: List[str]) -> Optional[str]:
        for label in labels:
            m = re.search(rf"{label}\s*[:\-]?\s*([A-Za-z0-9]+)", text, re.IGNORECASE)
            if m:
                return m.group(1)
        return None
