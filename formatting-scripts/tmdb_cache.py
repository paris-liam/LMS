"""On-disk cache of TMDB search responses, keyed by query + year.

The first pass over the full catalogue is thousands of requests. Every
correction pass afterwards re-reads the same rows, so without a cache the
fix-and-re-run loop pays the full rate-limited cost each time.

Failed requests are never cached — a network blip must not become a
permanent "no match".
"""

import json
from pathlib import Path


class TmdbCache:
    def __init__(self, path):
        self.path = Path(path)
        self.hits = 0
        self.misses = 0
        self._entries: dict[str, dict] = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._entries = loaded
            except (json.JSONDecodeError, OSError):
                self._entries = {}

    @staticmethod
    def _key(query: str, year: int | None) -> str:
        return f"{(query or '').strip().lower()}|{year if year is not None else ''}"

    def wrap(self, fetch_fn):
        """Return a fetch_fn(query, year) -> dict that consults the cache first."""

        def cached_fetch(query: str, year: int | None) -> dict:
            key = self._key(query, year)
            if key in self._entries:
                self.hits += 1
                return self._entries[key]
            data = fetch_fn(query, year)
            self._entries[key] = data
            self.misses += 1
            return data

        return cached_fetch

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._entries), encoding="utf-8")
