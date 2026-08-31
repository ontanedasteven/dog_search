from datetime import datetime, timedelta, timezone

from dog_monitor.models import Animal, MatchLevel


def make_animal(key="humane_broward:abc123"):
    return Animal(
        animal_key=key,
        source="humane_broward",
        region="Broward",
        url="https://example.com/pet/1",
        animal_id=None,
        name="Buddy",
        breed_text="Cairn Terrier",
        description="A good boy",
        weight=12.0,
        match_level=MatchLevel.EXACT,
        matched_term="Cairn Terrier",
    )


def test_unknown_animal_returns_none(db):
    assert db.get_animal("does-not-exist") is None


def test_insert_and_get_animal(db):
    animal = make_animal()
    is_new = db.upsert_animal(animal)
    assert is_new is True

    row = db.get_animal(animal.animal_key)
    assert row is not None
    assert row["name"] == "Buddy"
    assert row["match_level"] == "EXACT"
    assert row["matched_term"] == "Cairn Terrier"
    assert row["alert_sent"] is False
    assert row["active"] is True
    assert row["first_seen"] is not None
    assert row["last_seen"] is not None
    # Required fields per the persistence spec, stored directly on the
    # animal document (not just derivable from the doc ID or sightings).
    assert row["animal_key"] == animal.animal_key
    assert row["animal_id"] == animal.animal_id
    assert row["source"] == "humane_broward"
    assert row["region"] == "Broward"
    assert row["breed"] == "Cairn Terrier"
    assert row["weight"] == 12.0
    assert row["listing_url"] == "https://example.com/pet/1"


def test_sighting_recorded_per_source(db):
    animal = make_animal()
    db.upsert_animal(animal)

    sighting_ref = db._sightings().document(f"{animal.animal_key}__{animal.source}")
    sighting = sighting_ref.get().to_dict()
    assert sighting is not None
    assert sighting["region"] == "Broward"
    assert sighting["url"] == "https://example.com/pet/1"


def test_schema_init_is_implicit_and_repeatable(db):
    # Firestore is schemaless: collections/documents are created on first
    # write, so constructing FirestoreStore twice (or writing the same
    # animal twice) must never error.
    animal = make_animal()
    db.upsert_animal(animal)
    db.upsert_animal(animal)
    assert db.get_animal(animal.animal_key) is not None


def test_source_run_lifecycle_success(db):
    run_id = db.start_source_run("humane_broward")
    db.finish_source_run(run_id, success=True, animals_scanned=10, matches_found=2)

    row = db._source_runs().document(run_id).get().to_dict()
    assert row["success"] is True
    assert row["animals_scanned"] == 10
    assert row["matches_found"] == 2
    assert row["started_at"] is not None
    assert row["completed_at"] is not None


def test_source_run_failure_records_error_message(db):
    run_id = db.start_source_run("humane_miami")
    db.finish_source_run(run_id, success=False, error_message="boom: selectors changed")

    row = db._source_runs().document(run_id).get().to_dict()
    assert row["success"] is False
    assert row["error_message"] == "boom: selectors changed"


def test_last_successful_full_scan_is_none_when_never_run(db):
    assert db.get_last_successful_full_scan() is None


def test_last_successful_full_scan_round_trips(db):
    when = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    db.update_last_successful_full_scan(when)
    assert db.get_last_successful_full_scan() == when


def test_last_successful_full_scan_can_be_updated_repeatedly(db):
    first = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    second = first + timedelta(hours=96)
    db.update_last_successful_full_scan(first)
    db.update_last_successful_full_scan(second)
    assert db.get_last_successful_full_scan() == second


def test_update_last_successful_full_scan_defaults_to_now(db):
    before = datetime.now(timezone.utc)
    db.update_last_successful_full_scan()
    after = datetime.now(timezone.utc)
    recorded = db.get_last_successful_full_scan()
    assert before <= recorded <= after
