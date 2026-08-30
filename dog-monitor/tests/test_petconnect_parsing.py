from dog_monitor.matching import build_petconnect_key
from dog_monitor.scrapers.petconnect import PetConnectScraper


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
    assert scraper._detail_re.search("https://24petconnect.com/DetailsMain/BRWD/A2450160")
    assert not scraper._detail_re.search("https://24petconnect.com/DetailsMain/MIAD/A2450160")


def test_detail_url_regex_extracts_animal_id():
    scraper = PetConnectScraper(agency_code="MIAD", region="Miami-Dade")
    match = scraper._detail_re.search("https://24petconnect.com/DetailsMain/MIAD/A1234567")
    assert match is not None
    assert match.group(1).upper() == "A1234567"


def test_detail_url_regex_ignores_unrelated_links():
    scraper = PetConnectScraper(agency_code="BRWD", region="Broward")
    assert not scraper._detail_re.search("https://24petconnect.com/Search/Results?zip=33301")


def test_source_name_reflects_agency_case_insensitively():
    scraper = PetConnectScraper(agency_code="brwd", region="Broward")
    assert scraper.agency_code == "BRWD"
    assert scraper.source_name == "petconnect_brwd"
