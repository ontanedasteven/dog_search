"""Central registry of shelters/adoption platforms this monitor watches.

This is the file a contributor should edit to add, remove, enable, or
disable a source -- not `main.py` or any scraper module. Orchestration
(`main.build_scrapers`) simply iterates `enabled_sources()` and dispatches
each entry to the right scraper via `dog_monitor.scrapers.registry`, so
adding a source here (plus, if needed, a new adapter -- see
scrapers/registry.py) is normally the *only* change required.

Two identifiers matter here and they are intentionally different:

- `SourceConfig.id`: a human-facing registry slug (e.g. "humane-broward").
  Used for documentation, the README's "Current Coverage" table, and by
  humans editing this file. Free to rename.
- The scraper's own `source_name` (e.g. "humane_broward", set on the
  scraper class, not here): the stable identifier written into Firestore
  (`animals.source`, `sightings.source`, `source_runs.source`) and folded
  into dedup fingerprint keys for sources without a native ID. This must
  NOT change once a source has real data in Firestore, or existing
  animal/sighting documents become orphaned. Keep these two concepts
  separate rather than deriving one from the other.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class SourceConfig:
    """One shelter/agency this monitor watches.

    Attributes:
        id: Stable registry slug (kebab-case), human-facing only.
        name: Human-readable name, used in the alert email and README.
        region: Human-readable region label.
        type: Which scraping strategy this source uses -- must be a key
            in `scrapers.registry.SCRAPER_REGISTRY`. Currently "humane"
            (WordPress/CMS-style pet-card grid) or "24petconnect"
            (the 24petconnect.com platform, disambiguated by agency_code).
        enabled: Sources with enabled=False are skipped entirely by
            `enabled_sources()` -- disabling a source is a one-line edit
            here, no code change needed elsewhere.
        url: The listing page to scrape. Required for "humane"-type
            sources (there's no other way to find them). For
            "24petconnect"-type sources this is informational/documentary
            only -- PetConnectScraper derives the real listing URL from
            `agency_code`, since that's the platform's actual key.
        agency_code: The 24Petconnect agency code (required for
            "24petconnect"-type sources; the platform hosts many
            agencies/shelters behind the one domain, disambiguated by
            this code -- see https://24petconnect.com/<AGENCY_CODE>).
        parser: For "humane"-type sources, which adapter class handles
            this site's specific markup (registered in
            `scrapers.registry._HUMANE_PARSERS`). The two current Humane
            Society sites share a common card-grid scraping engine
            (`HumaneSocietyCardScraper`) but need different CSS
            selectors, so each gets a thin named subclass.
    """

    id: str
    name: str
    region: str
    type: str
    enabled: bool = True
    url: Optional[str] = None
    agency_code: Optional[str] = None
    parser: Optional[str] = None


# The reference implementation's current coverage: Miami-Dade County and
# Broward County, Florida. Extend this tuple to add sources -- see
# README.md's "Adding a Shelter" section for the full walkthrough.
SOURCES: Tuple[SourceConfig, ...] = (
    SourceConfig(
        id="humane-broward",
        name="Humane Society of Broward County",
        region="Broward County, FL",
        type="humane",
        url="https://humanebroward.com/all-pets/?pg=1",
        parser="humane_broward",
    ),
    SourceConfig(
        id="broward-animal-care",
        name="Broward County Animal Care",
        region="Broward County, FL",
        type="24petconnect",
        url="https://24petconnect.com/BRWD",
        agency_code="BRWD",
    ),
    SourceConfig(
        id="humane-miami",
        name="Humane Society of Greater Miami",
        region="Miami-Dade County, FL",
        type="humane",
        url="https://www.humanesocietymiami.org/adopt-a-pet-today/",
        parser="humane_miami",
    ),
    SourceConfig(
        id="miami-dade-animal-services",
        name="Miami-Dade Animal Services",
        region="Miami-Dade County, FL",
        type="24petconnect",
        url="https://24petconnect.com/MIAD",
        agency_code="MIAD",
    ),
)


def enabled_sources(sources: Tuple[SourceConfig, ...] = SOURCES) -> Tuple[SourceConfig, ...]:
    """The sources orchestration should actually run this cycle. Accepts an
    explicit `sources` tuple (defaulting to the real registry) so this
    filtering logic is trivially unit-testable without needing to mutate
    the global registry."""
    return tuple(s for s in sources if s.enabled)
