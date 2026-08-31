from dog_monitor.matching import build_petconnect_key
from dog_monitor.models import MatchLevel
from dog_monitor.scrapers.petconnect import PetConnectScraper, _TOTAL_RE


class FakeCard:
    """Minimal stand-in for a Playwright Locator, exposing just the
    get_attribute()/inner_text() surface PetConnectScraper._parse_card
    uses."""

    def __init__(self, card_id, text):
        self._id = card_id
        self._text = text

    def get_attribute(self, name):
        assert name == "id"
        return self._id

    def inner_text(self):
        return self._text


def test_agency_keys_are_namespaced():
    brwd_key = build_petconnect_key("BRWD", "A1234567")
    miad_key = build_petconnect_key("MIAD", "A1234567")
    assert brwd_key == "BRWD:A1234567"
    assert miad_key == "MIAD:A1234567"
    assert brwd_key != miad_key


def test_brwd_and_miad_are_treated_as_different_animals_for_same_id():
    brwd_key = build_petconnect_key("BRWD", "A1234567")
    miad_key = build_petconnect_key("MIAD", "A1234567")
    assert brwd_key != miad_key


def test_detail_url_regex_matches_own_agency_only():
    scraper = PetConnectScraper(agency_code="BRWD", region="Broward")
    assert scraper._detail_re.search("https://24petconnect.com/BRWD/Details/BRWD/A2450160")
    assert not scraper._detail_re.search("https://24petconnect.com/MIAD/Details/MIAD/A2450160")


def test_detail_url_regex_extracts_animal_id():
    scraper = PetConnectScraper(agency_code="MIAD", region="Miami-Dade")
    match = scraper._detail_re.search("https://24petconnect.com/MIAD/Details/MIAD/A1234567")
    assert match is not None
    assert match.group(1).upper() == "A1234567"


def test_detail_url_regex_ignores_unrelated_links():
    scraper = PetConnectScraper(agency_code="BRWD", region="Broward")
    assert not scraper._detail_re.search("https://24petconnect.com/Search/Results?zip=33301")


def test_detail_url_helper_builds_correct_url():
    scraper = PetConnectScraper(agency_code="brwd", region="Broward")
    assert scraper._detail_url("A2450160") == "https://24petconnect.com/BRWD/Details/BRWD/A2450160"


def test_source_name_reflects_agency_case_insensitively():
    scraper = PetConnectScraper(agency_code="brwd", region="Broward")
    assert scraper.agency_code == "BRWD"
    assert scraper.source_name == "petconnect_brwd"


def test_total_count_regex_parses_animals_line():
    m = _TOTAL_RE.search("Animals: 1 - 30 of 166")
    assert m is not None
    assert m.group(1) == "166"


def test_total_count_regex_ignores_unrelated_text():
    assert _TOTAL_RE.search("Nothing to see here") is None


def _card_text(name="ZEUS 4 (A1912983)", gender="Male", breed="Harrier and German Shepherd Dog", age="9 years old"):
    return (
        f"Name: {name}\n\n"
        f"Gender: {gender}\n\n"
        f"Breed: {breed}\n\n"
        "Animal type: Dog\n\n"
        f"Age: {age}\n\n"
        "Brought to the shelter: 2026.07.27\n\n"
        "Located at: Broward County Animal Care - Ft Lauderdale"
    )


def test_parse_card_extracts_fields_and_strips_id_from_name():
    scraper = PetConnectScraper(agency_code="BRWD", region="Broward")
    card = FakeCard("Result_A1912983", _card_text())
    animal = scraper._parse_card(card)
    assert animal is not None
    assert animal.animal_id == "A1912983"
    assert animal.name == "ZEUS 4"
    assert animal.sex == "Male"
    assert animal.breed_text == "Harrier and German Shepherd Dog"
    assert animal.age == "9 years old"
    assert animal.animal_key == "BRWD:A1912983"
    assert animal.url == "https://24petconnect.com/BRWD/Details/BRWD/A1912983"
    assert animal.match_level == MatchLevel.NONE


def test_parse_card_classifies_matching_breed():
    scraper = PetConnectScraper(agency_code="BRWD", region="Broward")
    card = FakeCard("Result_A2450160", _card_text(name="BUDDY (A2450160)", breed="Cairn Terrier"))
    animal = scraper._parse_card(card)
    assert animal is not None
    assert animal.match_level == MatchLevel.EXACT
    assert animal.matched_term == "Cairn Terrier"


def test_parse_card_returns_none_for_unrecognized_card_id():
    scraper = PetConnectScraper(agency_code="BRWD", region="Broward")
    card = FakeCard("SomeOtherElement", _card_text())
    assert scraper._parse_card(card) is None
