"""A minimal in-memory stand-in for google.cloud.firestore.Client.

Implements only the narrow subset of the real API that dog_monitor.database
uses (collection/document/get/set/update, exists/to_dict, auto-generated
document IDs). This keeps the unit test suite fast and dependency-free (no
network, no emulator, no GCP credentials required) while exercising the
exact same code path FirestoreStore uses in production.

This is NOT a full Firestore emulator: it does not model transactions,
queries, security rules, or server timestamps. Before deploying, also
validate against the real Firestore emulator or a real project (see
README.md's "Local development and testing" section).
"""

import itertools
from typing import Any, Dict, Optional


class _FakeSnapshot:
    def __init__(self, doc_id: str, data: Optional[Dict[str, Any]]):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return dict(self._data) if self._data is not None else None


class _FakeDocumentRef:
    def __init__(self, collection: "_FakeCollection", doc_id: str):
        self._collection = collection
        self.id = doc_id

    def get(self) -> _FakeSnapshot:
        data = self._collection._docs.get(self.id)
        return _FakeSnapshot(self.id, data)

    def set(self, data: Dict[str, Any], merge: bool = False) -> None:
        existing = self._collection._docs.get(self.id)
        if merge and existing is not None:
            merged = dict(existing)
            merged.update(data)
            self._collection._docs[self.id] = merged
        else:
            self._collection._docs[self.id] = dict(data)

    def update(self, data: Dict[str, Any]) -> None:
        existing = self._collection._docs.get(self.id)
        if existing is None:
            raise KeyError(f"No document to update: {self.id}")
        merged = dict(existing)
        merged.update(data)
        self._collection._docs[self.id] = merged


class _FakeCollection:
    def __init__(self, name: str):
        self.name = name
        self._docs: Dict[str, Dict[str, Any]] = {}
        self._id_counter = itertools.count(1)

    def document(self, doc_id: Optional[str] = None) -> _FakeDocumentRef:
        if doc_id is None:
            doc_id = f"auto_{next(self._id_counter)}"
        return _FakeDocumentRef(self, doc_id)


class FakeFirestoreClient:
    def __init__(self):
        self._collections: Dict[str, _FakeCollection] = {}

    def collection(self, name: str) -> _FakeCollection:
        if name not in self._collections:
            self._collections[name] = _FakeCollection(name)
        return self._collections[name]

    def close(self) -> None:
        pass
