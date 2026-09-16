"""On-disk cache of UPCMDB lookups, keyed by IMDb ID.

UPCMDB quota is limited (unlike TMDB), so every re-run over the same rows
(re-trying after a matching fix, testing on an overlapping --limit slice,
etc.) must not re-spend quota on an IMDb ID already looked up. A 404 (no
UPC records for that IMDb ID) is a real, stable answer -- not a transient
failure -- so it's cached too, as an empty list. Only actual request
failures (network errors, non-404 HTTP errors) are left uncached, same
policy as tmdb_cache.py.
"""

import json
from pathlib import Path


class UpcmdbCache:
    def __init__(self, path):
        self.path = Path(path)
        self.hits = 0
        self.misses = 0
        self._entries: dict[str, list] = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._entries = loaded
            except (json.JSONDecodeError, OSError):
                self._entries = {}

    @staticmethod
    def _key(imdb_id: str) -> str:
        return (imdb_id or "").strip().lower()

    def wrap(self, fetch_fn):
        """Return a fetch_fn(imdb_id) -> list[dict] that consults the cache first."""

        def cached_fetch(imdb_id: str) -> list:
            key = self._key(imdb_id)
            if key in self._entries:
                self.hits += 1
                return self._entries[key]
            data = fetch_fn(imdb_id)
            self._entries[key] = data
            self.misses += 1
            return data

        return cached_fetch

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._entries), encoding="utf-8")
