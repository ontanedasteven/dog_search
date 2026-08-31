from dog_monitor.models import Animal, MatchLevel


def make_animal(url="https://24petconnect.com/DetailsMain/BRWD/A2450160"):
    return Animal(
        animal_key="BRWD:A2450160",
        source="petconnect_brwd",
        region="Broward",
        url=url,
        animal_id="A2450160",
        name="Buddy",
        breed_text="Cairn Terrier",
        description="A good boy",
        weight=12.0,
        match_level=MatchLevel.EXACT,
        matched_term="Cairn Terrier",
    )


def test_first_sighting_is_new(db):
    animal = make_animal()
    assert db.upsert_animal(animal) is True


def test_second_sighting_of_same_animal_is_not_new(db):
    animal = make_animal()
    db.upsert_animal(animal)
    assert db.upsert_animal(animal) is False


def test_second_sighting_updates_description_and_url(db):
    animal = make_animal()
    db.upsert_animal(animal)

    updated = make_animal(url="https://24petconnect.com/DetailsMain/BRWD/A2450160?refresh=1")
    updated.description = "Updated: now even friendlier"
    db.upsert_animal(updated)

    row = db.get_animal(animal.animal_key)
    assert row["description"] == "Updated: now even friendlier"

    sighting = db._sightings().document(f"{animal.animal_key}__{animal.source}").get().to_dict()
    assert sighting["url"] == updated.url


def test_new_unalerted_animal_should_alert(db):
    animal = make_animal()
    db.upsert_animal(animal)
    assert db.should_alert(animal.animal_key) is True


def test_same_animal_does_not_generate_two_alerts(db):
    animal = make_animal()
    db.upsert_animal(animal)
    db.mark_alert_sent(animal.animal_key)

    # Animal is seen again on a later run.
    db.upsert_animal(animal)

    assert db.should_alert(animal.animal_key) is False


def test_failed_email_leaves_alert_sent_false(db):
    animal = make_animal()
    db.upsert_animal(animal)
    # Simulate a failed send: mark_alert_sent is deliberately NOT called.
    row = db.get_animal(animal.animal_key)
    assert row["alert_sent"] is False
    assert db.should_alert(animal.animal_key) is True


def test_successful_email_marks_alert_sent(db):
    animal = make_animal()
    db.upsert_animal(animal)
    db.mark_alert_sent(animal.animal_key)
    row = db.get_animal(animal.animal_key)
    assert row["alert_sent"] is True
    assert db.should_alert(animal.animal_key) is False


def test_unknown_animal_is_not_alertable(db):
    assert db.should_alert("BRWD:A9999999") is False
