"""On-disk cache of TMDB search responses, keyed by query + year, shared by
every run (runs/.tmdb-cache.json).

Saved every `save_every` new fetches and atomically (temp file + rename), so
an interrupted audit keeps its work and a crash mid-write never corrupts the
file. Failed requests are never cached — a network blip must not become a
permanent "no match".
"""

import json
from pathlib import Path


class TmdbCache:
    def __init__(self, path, save_every: int = 50):
        self.path = Path(path)
        self.save_every = save_every
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
        def cached_fetch(query: str, year: int | None) -> dict:
            key = self._key(query, year)
            if key in self._entries:
                self.hits += 1
                return self._entries[key]
            data = fetch_fn(query, year)
            self._entries[key] = data
            self.misses += 1
            if self.save_every and self.misses % self.save_every == 0:
                self.save()
            return data

        return cached_fetch

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._entries), encoding="utf-8")
        tmp.replace(self.path)
