"""Reusable 24Petconnect scraper, parameterized by agency code.

Both Broward County Animal Care (BRWD) and Miami-Dade Animal Services
(MIAD) publish through the same 24petconnect.com platform, so a single
implementation covers both required sources.

IMPORTANT SELECTOR CAVEAT: this project was built in a sandboxed
environment with no outbound network access to 24petconnect.com, so the
search-workflow selectors below (species filter, location field, search
button) are best-effort guesses and were NOT verified against the live
site. If a run logs "Search workflow failed" or "No detail links found",
inspect the live DOM (devtools) and update the candidate selector lists in
`_run_search`. The detail-page-URL pattern and field-extraction logic are
markup-light (based on visible text + the documented URL shape
`/DetailsMain/<AGENCY>/<ID>`) and should need little adjustment.
"""

import logging
import re
import time
from typing import List, Optional, Set

from playwright.sync_api import Browser, Page

from ..matching import build_petconnect_key, classify_breed, extract_animal_id, extract_weight
from ..models import Animal
from .base import BaseScraper, ScraperError

logger = logging.getLogger(__name__)

BASE_URL = "https://24petconnect.com/"

# A broad enough South Florida search to cover both agencies' service areas.
SEARCH_LOCATIONS = ["Miami, FL", "Fort Lauderdale, FL"]

# Detail pages are visited in small batches with a short pause between each
# to keep load on the site modest and stay Raspberry-Pi resource friendly.
# (Sync Playwright is not thread-safe across browser objects, so true
# parallel tabs would require a separate browser process per worker; batching
# with short delays achieves the "don't hammer the site" goal without that
# overhead.)
DETAIL_PAGE_CONCURRENCY = 5
DETAIL_PAGE_DELAY_SECONDS = 0.6
SEARCH_STEP_DELAY_SECONDS = 1.0


class PetConnectScraper(BaseScraper):
    def __init__(self, agency_code: str, region: str, headless: bool = True, timeout_ms: int = 30000):
        super().__init__(headless=headless, timeout_ms=timeout_ms)
        self.agency_code = agency_code.upper()
        self.region = region
        self.source_name = f"petconnect_{self.agency_code.lower()}"
        self._detail_re = re.compile(
            rf"/DetailsMain/{re.escape(self.agency_code)}/([A-Za-z]\d{{6,8}})", re.IGNORECASE
        )

    def scrape(self, browser: Browser) -> List[Animal]:
        detail_urls = self._collect_detail_urls(browser)
        if not detail_urls:
            raise ScraperError(
                f"[{self.source_name}] No detail links found for agency "
                f"{self.agency_code} on 24Petconnect. The search workflow may "
                "have changed; see scrapers/petconnect.py for selectors to update."
            )
        logger.info("[%s] Found %d detail links to visit", self.source_name, len(detail_urls))

        animals: List[Animal] = []
        for i in range(0, len(detail_urls), DETAIL_PAGE_CONCURRENCY):
            batch = detail_urls[i : i + DETAIL_PAGE_CONCURRENCY]
            for url in batch:
                animal = self._scrape_detail_page(browser, url)
                if animal is not None:
                    animals.append(animal)
                time.sleep(DETAIL_PAGE_DELAY_SECONDS)
        return animals

    def _collect_detail_urls(self, browser: Browser) -> List[str]:
        found: Set[str] = set()
        page = browser.new_page()
        try:
            page.set_default_timeout(self.timeout_ms)
            for location in SEARCH_LOCATIONS:
                try:
                    self._run_search(page, location)
                    found.update(self._extract_agency_links(page))
                except Exception:
                    logger.warning(
                        "[%s] Search workflow failed for location '%s'",
                        self.source_name, location, exc_info=True,
                    )
                    continue
                time.sleep(SEARCH_STEP_DELAY_SECONDS)
        finally:
            page.close()
        return sorted(found)

    def _run_search(self, page: Page, location: str) -> None:
        logger.info("[%s] Searching 24Petconnect near '%s'", self.source_name, location)
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        for selector in ("text=/^dogs?$/i", "[data-species='Dog']", "#species-dog"):
            try:
                locator = page.locator(selector)
                if locator.count() > 0:
                    locator.first.click(timeout=3000)
                    break
            except Exception:
                continue

        filled = False
        for selector in (
            "input[name='location']",
            "input[placeholder*='zip' i]",
            "input[placeholder*='city' i]",
            "#location",
        ):
            try:
                locator = page.locator(selector)
                if locator.count() > 0:
                    locator.first.fill(location, timeout=3000)
                    filled = True
                    break
            except Exception:
                continue
        if not filled:
            raise ScraperError(f"[{self.source_name}] Could not locate a location/zip search field.")

        clicked = False
        for selector in ("button:has-text('Search')", "input[type='submit']", "text=/^search$/i"):
            try:
                locator = page.locator(selector)
                if locator.count() > 0:
                    locator.first.click(timeout=3000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            page.keyboard.press("Enter")

        page.wait_for_timeout(4000)
        self._scroll_for_more_results(page)

    def _scroll_for_more_results(self, page: Page) -> None:
        last_height = 0
        for _ in range(10):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(500)
            try:
                height = page.evaluate("document.body.scrollHeight")
            except Exception:
                break
            if height == last_height:
                break
            last_height = height

    def _extract_agency_links(self, page: Page) -> List[str]:
        try:
            hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        except Exception:
            return []
        return [href for href in hrefs if self._detail_re.search(href)]

    def _scrape_detail_page(self, browser: Browser, url: str) -> Optional[Animal]:
        page = browser.new_page()
        try:
            page.set_default_timeout(self.timeout_ms)
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            text = (page.inner_text("body") or "").strip()
            if not text:
                logger.warning("[%s] Empty detail page body for %s", self.source_name, url)
                return None

            id_match = self._detail_re.search(url)
            animal_id = id_match.group(1).upper() if id_match else extract_animal_id(text)
            if not animal_id:
                logger.warning("[%s] Could not extract animal ID from %s; skipping.", self.source_name, url)
                return None

            name = None
            name_el = page.query_selector("h1, h2, .pet-name, .animal-name")
            if name_el:
                try:
                    name = (name_el.inner_text() or "").strip() or None
                except Exception:
                    name = None

            breed_text = self._extract_field(text, ["breed"]) or text
            age = self._extract_field(text, ["age"])
            sex = self._extract_field(text, ["sex", "gender"])
            weight = extract_weight(self._extract_field(text, ["weight"]) or text)
            shelter = self._extract_field(text, ["shelter", "location"])

            img_el = page.query_selector("img")
            image_url = img_el.get_attribute("src") if img_el else None

            match = classify_breed(breed_text, weight=weight)
            animal_key = build_petconnect_key(self.agency_code, animal_id)

            description_parts = [text[:2000]]
            if shelter:
                description_parts.append(f"Shelter/location: {shelter}")

            return Animal(
                animal_key=animal_key,
                source=self.source_name,
                region=self.region,
                url=url,
                animal_id=animal_id,
                name=name,
                breed_text=breed_text,
                description="\n".join(description_parts),
                age=age,
                sex=sex,
                weight=match.weight,
                image_url=image_url,
                match_level=match.level,
                matched_term=match.matched_term,
            )
        except Exception:
            logger.warning("[%s] Failed to scrape detail page %s", self.source_name, url, exc_info=True)
            return None
        finally:
            page.close()

    @staticmethod
    def _extract_field(text: str, labels: List[str]) -> Optional[str]:
        for label in labels:
            m = re.search(rf"{label}\s*[:\-]\s*([^\n]+)", text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None
