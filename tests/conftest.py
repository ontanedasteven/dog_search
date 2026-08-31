import pytest

from dog_monitor.database import FirestoreStore
from tests.fakes import FakeFirestoreClient


@pytest.fixture
def db():
    store = FirestoreStore(client=FakeFirestoreClient())
    yield store
    store.close()
