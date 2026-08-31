"""Tests for the 96-hour full-scan guard (main.is_scan_due).

Cloud Scheduler may invoke the Cloud Run Job daily, but a full shelter scan
must only happen once every 96 hours. These tests exercise that rolling
window directly against FirestoreStore (backed by the in-memory fake), with
no Playwright/network involvement.
"""

from datetime import datetime, timedelta, timezone

from dog_monitor.database import FirestoreStore
from dog_monitor.main import FULL_SCAN_INTERVAL_HOURS, is_scan_due
from tests.fakes import FakeFirestoreClient


def make_db():
    return FirestoreStore(client=FakeFirestoreClient())


def test_scan_is_due_when_never_run():
    db = make_db()
    assert is_scan_due(db) is True


def test_scan_not_due_shortly_after_a_scan():
    db = make_db()
    db.update_last_successful_full_scan(datetime.now(timezone.utc) - timedelta(hours=1))
    assert is_scan_due(db) is False


def test_scan_not_due_at_10_hours():
    db = make_db()
    db.update_last_successful_full_scan(datetime.now(timezone.utc) - timedelta(hours=10))
    assert is_scan_due(db) is False


def test_scan_not_due_just_under_96_hours():
    db = make_db()
    db.update_last_successful_full_scan(
        datetime.now(timezone.utc) - timedelta(hours=FULL_SCAN_INTERVAL_HOURS - 1)
    )
    assert is_scan_due(db) is False


def test_scan_due_at_exactly_96_hours():
    db = make_db()
    db.update_last_successful_full_scan(
        datetime.now(timezone.utc) - timedelta(hours=FULL_SCAN_INTERVAL_HOURS)
    )
    assert is_scan_due(db) is True


def test_scan_due_after_96_hours():
    db = make_db()
    db.update_last_successful_full_scan(
        datetime.now(timezone.utc) - timedelta(hours=FULL_SCAN_INTERVAL_HOURS + 1)
    )
    assert is_scan_due(db) is True


def test_scan_due_after_many_days():
    db = make_db()
    db.update_last_successful_full_scan(datetime.now(timezone.utc) - timedelta(days=30))
    assert is_scan_due(db) is True


def test_custom_interval_is_respected():
    db = make_db()
    db.update_last_successful_full_scan(datetime.now(timezone.utc) - timedelta(hours=5))
    assert is_scan_due(db, interval_hours=1) is True
    assert is_scan_due(db, interval_hours=10) is False
