"""Tests for HumaneSocietyCardScraper._extract_age/_extract_sex against the
real (unlabelled) text formats confirmed live on both Humane Society sites
on 2026-08-31, and a regression guard for the Broward card-selector
duplicate-count bug (div.pet-item vs. its nested a.pet-item-link, both of
which match the substring selector [class*='pet-item'])."""

from dog_monitor.scrapers.base import HumaneSocietyCardScraper
from dog_monitor.scrapers.humane_broward import HumaneBrowardScraper

BROWARD_CARD_TEXT = (
    "Blu\nA617280\nDomestic Shorthair Mix\nMale\n7 years – 11.00 lbs."
    "\nBlack and White Color\nHumane Society of Broward County"
)
BROWARD_CARD_TEXT_NO_AGE = (
    "Hannah\nA692906\nShorthaired Rabbit\nFemale\nno age – 4.80 lbs."
    "\nBrown Color\nHumane Society of Broward County"
)
MIAMI_CARD_TEXT = (
    "DOG\nAlexa\n\nTerrier, American Pit Bull\n\n●\n3 years 8 months 14 days"
    "\n●\nFemale\n●\n64 pounds\nMeet Alexa"
)
MIAMI_CARD_TEXT_SHORT_AGE = (
    "DOG\nBella\n\nGerman Shepherd\n\n●\n9 months 9 days\n●\nFemale"
    "\n●\n47 pounds\nMeet Bella"
)


def test_extract_sex_finds_bare_male():
    assert HumaneSocietyCardScraper._extract_sex(BROWARD_CARD_TEXT) == "Male"


def test_extract_sex_finds_bare_female():
    assert HumaneSocietyCardScraper._extract_sex(MIAMI_CARD_TEXT) == "Female"


def test_extract_sex_returns_none_when_absent():
    assert HumaneSocietyCardScraper._extract_sex("No gender info here") is None


def test_extract_age_broward_years_and_weight_on_one_line():
    assert HumaneSocietyCardScraper._extract_age(BROWARD_CARD_TEXT) == "7 years"


def test_extract_age_does_not_match_weight():
    # "no age -- 4.80 lbs." must not accidentally yield an age from the
    # weight figure.
    assert HumaneSocietyCardScraper._extract_age(BROWARD_CARD_TEXT_NO_AGE) is None


def test_extract_age_miami_chained_years_months_days():
    assert HumaneSocietyCardScraper._extract_age(MIAMI_CARD_TEXT) == "3 years 8 months 14 days"


def test_extract_age_miami_months_and_days_only():
    assert HumaneSocietyCardScraper._extract_age(MIAMI_CARD_TEXT_SHORT_AGE) == "9 months 9 days"


def test_broward_card_selector_is_exact_class_not_wildcard():
    # Regression guard: `[class*='pet-item']` matches both div.pet-item AND
    # its own nested a.pet-item-link, double-counting every animal. The
    # first candidate must be the tag-scoped, exact-class selector.
    assert HumaneBrowardScraper.card_selectors[0] == "div.pet-item"
