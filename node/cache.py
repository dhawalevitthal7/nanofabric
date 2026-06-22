from collections import OrderedDict


class Cache:
    """LRU cache storing block records with version and tombstone metadata."""

    def __init__(self, max_entries=10_000):
        self._max = max_entries
        self._store = OrderedDict()

    def put(self, key, record):
        self._store[key] = record
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def get(self, key):
        record = self._store.get(key)
        if record is not None:
            self._store.move_to_end(key)
        return record

    def remove(self, key):
        self._store.pop(key, None)

    def __len__(self):
        return len(self._store)
