"""Reusable 24Petconnect scraper, parameterized by agency code.

Both Broward County Animal Care (BRWD) and Miami-Dade Animal Services
(MIAD) publish through the same 24petconnect.com platform, so a single
implementation covers both required sources.

Verified live against https://24petconnect.com/BRWD on 2026-08-31:

- No location search is needed at all -- each agency has a direct listing
  page at `https://24petconnect.com/<AGENCY>` that renders all of that
  agency's animals (client-side rendered; Playwright waits for
  `networkidle`).
- Each animal is a `div.gridResult` card whose `id` attribute is
  `Result_<ANIMAL_ID>` (e.g. `Result_A1912983`), containing labelled text
  lines (`Name:`, `Gender:`, `Breed:`, `Animal type:`, `Age:`,
  `Located at:`) -- no weight field on the list page.
- Pagination is 30 animals/page via a JS call `MoreAnimals('<offset>',
  '<AGENCY>', '')` that *replaces* the grid in place (confirmed: zero ID
  overlap between offset=0 and offset=30). The total count is stated in
  the page as "Animals: X - Y of <TOTAL>".
- Each animal's detail page is `https://24petconnect.com/<AGENCY>/Details/
  <AGENCY>/<ANIMAL_ID>` (a real, directly navigable URL) and contains a
  free-text description including weight, e.g. "I weigh 53 pounds."

To keep load on the site modest, only animals whose list-page breed text
already matches (EXACT/STRONG/POSSIBLE) get a detail-page visit -- for
weight (to refine/confirm a POSSIBLE match) and a richer description for
the alert email. Non-matching animals (the large majority) never trigger a
second page load.
"""

import logging
import re
import time
from typing import List, Optional

from playwright.sync_api import Browser, Page

from ..matching import build_petconnect_key, classify_breed, extract_weight
from ..models import Animal, MatchLevel
from .base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

PAGE_SIZE = 30
# Safety cap on pages fetched even if the "of <TOTAL>" count can't be
# parsed, so a markup change can't spin this into an unbounded loop.
MAX_PAGES = 30

PAGE_LOAD_DELAY_SECONDS = 1.0
DETAIL_PAGE_DELAY_SECONDS = 0.4
DETAIL_PAGE_RENDER_WAIT_MS = 800

_TOTAL_RE = re.compile(r"Animals:\s*\d+\s*-\s*\d+\s*of\s*(\d+)", re.IGNORECASE)
_CARD_ID_RE = re.compile(r"^Result_([A-Za-z]\d{6,8})$", re.IGNORECASE)


class PetConnectScraper(BaseScraper):
    def __init__(self, agency_code: str, region: str, headless: bool = True, timeout_ms: int = 30000):
        super().__init__(headless=headless, timeout_ms=timeout_ms)
        self.agency_code = agency_code.upper()
        self.region = region
        self.source_name = f"petconnect_{self.agency_code.lower()}"
        self.list_url = f"https://24petconnect.com/{self.agency_code}"
        # Matches this agency's real, directly-navigable detail page URL:
        # https://24petconnect.com/<AGENCY>/Details/<AGENCY>/<ID>
        self._detail_re = re.compile(
            rf"/{re.escape(self.agency_code)}/Details/{re.escape(self.agency_code)}/([A-Za-z]\d{{6,8}})",
            re.IGNORECASE,
        )

    def _detail_url(self, animal_id: str) -> str:
        return f"https://24petconnect.com/{self.agency_code}/Details/{self.agency_code}/{animal_id}"

    def scrape(self, browser: Browser) -> List[Animal]:
        page = browser.new_page()
        try:
            page.set_default_timeout(self.timeout_ms)
            animals = self._collect_list_animals(page)
        finally:
            page.close()

        if not animals:
            raise ScraperError(
                f"[{self.source_name}] No animal cards found for agency "
                f"{self.agency_code} on 24Petconnect (div.gridResult). The "
                "site markup may have changed; see scrapers/petconnect.py."
            )

        for animal in animals:
            if animal.match_level != MatchLevel.NONE:
                self._enrich_from_detail(browser, animal)

        return animals

    def _collect_list_animals(self, page: Page) -> List[Animal]:
        logger.info("[%s] Loading %s", self.source_name, self.list_url)
        page.goto(self.list_url, wait_until="networkidle")
        page.wait_for_timeout(2000)

        total = self._parse_total(page)
        animals: List[Animal] = []
        offset = 0
        pages_fetched = 0

        while pages_fetched < MAX_PAGES:
            if offset > 0:
                try:
                    page.evaluate(
                        "([offset, agency]) => MoreAnimals(offset, agency, '')",
                        [str(offset), self.agency_code],
                    )
                except Exception:
                    logger.warning(
                        "[%s] Pagination call failed at offset=%d; stopping pagination.",
                        self.source_name, offset, exc_info=True,
                    )
                    break
                page.wait_for_timeout(int(PAGE_LOAD_DELAY_SECONDS * 1000))

            cards = page.locator("div.gridResult")
            count = cards.count()
            if count == 0:
                break

            for i in range(count):
                animal = self._parse_card(cards.nth(i))
                if animal is not None:
                    animals.append(animal)

            pages_fetched += 1
            offset += PAGE_SIZE
            if total is not None and offset >= total:
                break
            time.sleep(PAGE_LOAD_DELAY_SECONDS)

        logger.info(
            "[%s] Collected %d animal(s) across %d page(s) (reported total=%s)",
            self.source_name, len(animals), pages_fetched, total,
        )
        return animals

    @staticmethod
    def _parse_total(page: Page) -> Optional[int]:
        try:
            body_text = page.inner_text("body")
        except Exception:
            return None
        m = _TOTAL_RE.search(body_text or "")
        return int(m.group(1)) if m else None

    def _parse_card(self, card) -> Optional[Animal]:
        try:
            card_id = card.get_attribute("id") or ""
            text = (card.inner_text() or "").strip()
        except Exception:
            return None

        id_match = _CARD_ID_RE.match(card_id)
        if not id_match or not text:
            return None
        animal_id = id_match.group(1).upper()

        name = self._extract_field(text, ["name"])
        if name:
            # List text is like "ZEUS 4 (A1912983)" -- strip the trailing ID.
            name = re.sub(r"\s*\([A-Za-z]\d{6,8}\)\s*$", "", name).strip() or name
        sex = self._extract_field(text, ["gender"])
        breed_text = self._extract_field(text, ["breed"])
        age = self._extract_field(text, ["age"])

        match = classify_breed(breed_text or "", weight=None)
        animal_key = build_petconnect_key(self.agency_code, animal_id)

        return Animal(
            animal_key=animal_key,
            source=self.source_name,
            region=self.region,
            url=self._detail_url(animal_id),
            animal_id=animal_id,
            name=name,
            breed_text=breed_text,
            description=text[:2000],
            age=age,
            sex=sex,
            weight=match.weight,
            match_level=match.level,
            matched_term=match.matched_term,
        )

    def _enrich_from_detail(self, browser: Browser, animal: Animal) -> None:
        """For a list-page match, visit its detail page to pick up a weight
        (refining/confirming a POSSIBLE match) and a fuller description.
        Never raises -- enrichment failure just leaves the list-page data
        (and match_level) as-is."""
        page = browser.new_page()
        try:
            page.set_default_timeout(self.timeout_ms)
            page.goto(animal.url, wait_until="domcontentloaded")
            page.wait_for_timeout(DETAIL_PAGE_RENDER_WAIT_MS)
            text = (page.inner_text("body") or "").strip()
            if not text:
                return

            weight = extract_weight(text)
            if weight is not None:
                match = classify_breed(animal.breed_text or "", weight=weight)
                animal.weight = weight
                animal.match_level = match.level
                animal.matched_term = match.matched_term or animal.matched_term

            animal.description = text[:2000]
            time.sleep(DETAIL_PAGE_DELAY_SECONDS)
        except Exception:
            logger.warning(
                "[%s] Failed to enrich detail page for %s (%s); keeping list-page data.",
                self.source_name, animal.animal_id, animal.url, exc_info=True,
            )
        finally:
            page.close()

    @staticmethod
    def _extract_field(text: str, labels: List[str]) -> Optional[str]:
        for label in labels:
            m = re.search(rf"^{label}\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
            if m:
                return m.group(1).strip()
        return None
