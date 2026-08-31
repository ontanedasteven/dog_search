"""Tests for the source registry (sources.py) and scraper dispatch
(scrapers/registry.py). These exist to catch registry-editing mistakes
early -- a contributor adding a shelter by hand-editing sources.py gets a
clear test failure instead of a silent skip or a startup crash in
production."""

import pytest

from dog_monitor.scrapers.humane_broward import HumaneBrowardScraper
from dog_monitor.scrapers.humane_miami import HumaneMiamiScraper
from dog_monitor.scrapers.petconnect import PetConnectScraper
from dog_monitor.scrapers.registry import SCRAPER_REGISTRY, build_scraper
from dog_monitor.sources import SOURCES, SourceConfig, enabled_sources


def test_all_source_ids_are_unique():
    ids = [s.id for s in SOURCES]
    assert len(ids) == len(set(ids))


def test_all_enabled_sources_have_required_fields():
    for source in enabled_sources():
        assert source.id, f"{source} is missing id"
        assert source.name, f"{source} is missing name"
        assert source.region, f"{source} is missing region"
        assert source.type, f"{source} is missing type"


def test_24petconnect_sources_have_agency_code():
    petconnect_sources = [s for s in SOURCES if s.type == "24petconnect"]
    assert petconnect_sources, "expected at least one 24petconnect source"
    for source in petconnect_sources:
        assert source.agency_code, f"{source.id} is a 24petconnect source with no agency_code"


def test_humane_sources_have_url_and_parser():
    humane_sources = [s for s in SOURCES if s.type == "humane"]
    assert humane_sources, "expected at least one humane source"
    for source in humane_sources:
        assert source.url, f"{source.id} is a humane source with no url"
        assert source.parser, f"{source.id} is a humane source with no parser"


def test_brwd_agency_is_registered():
    assert any(s.agency_code == "BRWD" for s in SOURCES)


def test_miad_agency_is_registered():
    assert any(s.agency_code == "MIAD" for s in SOURCES)


def test_scraper_registry_recognizes_every_enabled_source_type():
    for source in enabled_sources():
        assert source.type in SCRAPER_REGISTRY, (
            f"source {source.id!r} has type {source.type!r}, which has no "
            f"factory in SCRAPER_REGISTRY ({sorted(SCRAPER_REGISTRY)})"
        )


def test_build_scraper_dispatches_humane_sources_to_correct_class():
    broward = next(s for s in SOURCES if s.id == "humane-broward")
    miami = next(s for s in SOURCES if s.id == "humane-miami")
    assert isinstance(build_scraper(broward, headless=True), HumaneBrowardScraper)
    assert isinstance(build_scraper(miami, headless=True), HumaneMiamiScraper)


def test_build_scraper_dispatches_24petconnect_sources_to_petconnect_scraper():
    brwd = next(s for s in SOURCES if s.agency_code == "BRWD")
    scraper = build_scraper(brwd, headless=True)
    assert isinstance(scraper, PetConnectScraper)
    assert scraper.agency_code == "BRWD"


def test_build_scraper_preserves_stable_source_name_for_existing_firestore_data():
    # These exact strings are already written into production Firestore
    # documents (animals.source, sightings.source, source_runs.source,
    # and dedup fingerprint keys). Changing them would orphan existing data.
    expected = {
        "humane-broward": "humane_broward",
        "humane-miami": "humane_miami",
        "broward-animal-care": "petconnect_brwd",
        "miami-dade-animal-services": "petconnect_miad",
    }
    for source_id, expected_source_name in expected.items():
        source = next(s for s in SOURCES if s.id == source_id)
        scraper = build_scraper(source, headless=True)
        assert scraper.source_name == expected_source_name


def test_build_scraper_raises_for_unregistered_type():
    bogus = SourceConfig(id="bogus", name="Bogus", region="Nowhere", type="not-a-real-type")
    with pytest.raises(ValueError):
        build_scraper(bogus, headless=True)


def test_build_scraper_raises_for_24petconnect_missing_agency_code():
    bad = SourceConfig(id="bad", name="Bad", region="Nowhere", type="24petconnect")
    with pytest.raises(ValueError):
        build_scraper(bad, headless=True)


def test_build_scraper_raises_for_humane_unknown_parser():
    bad = SourceConfig(
        id="bad", name="Bad", region="Nowhere", type="humane",
        url="https://example.com", parser="does-not-exist",
    )
    with pytest.raises(ValueError):
        build_scraper(bad, headless=True)


def test_enabled_sources_skips_disabled_entries():
    fake_sources = (
        SourceConfig(id="a", name="A", region="X", type="humane", url="https://a", parser="humane_broward", enabled=True),
        SourceConfig(id="b", name="B", region="X", type="humane", url="https://b", parser="humane_broward", enabled=False),
        SourceConfig(id="c", name="C", region="X", type="24petconnect", agency_code="C", enabled=True),
    )
    result = enabled_sources(fake_sources)
    assert [s.id for s in result] == ["a", "c"]


def test_all_current_sources_are_enabled():
    # The reference implementation's four sources should all be active by
    # default; a disabled entry here would silently reduce coverage.
    assert all(s.enabled for s in SOURCES)


def test_orchestration_skips_disabled_sources(monkeypatch):
    """main.build_scrapers() must not instantiate a scraper for a
    disabled source -- this exercises the actual orchestration path
    (not just the enabled_sources() filter it's built on)."""
    from dog_monitor import main as main_module

    fake_sources = (
        SourceConfig(id="on", name="On", region="X", type="humane", url="https://on", parser="humane_broward", enabled=True),
        SourceConfig(id="off", name="Off", region="X", type="humane", url="https://off", parser="humane_miami", enabled=False),
    )
    monkeypatch.setattr(main_module, "enabled_sources", lambda: enabled_sources(fake_sources))

    scrapers = main_module.build_scrapers(headless=True)
    assert len(scrapers) == 1
    assert isinstance(scrapers[0], HumaneBrowardScraper)
