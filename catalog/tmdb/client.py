"""The real, network-hitting TMDB search fetcher. Sleeps after every request
(hit the API politely); cache hits never reach it, so they never sleep."""

import json
import time
import urllib.parse
import urllib.request

from catalog.tmdb.match import REQUEST_DELAY_SECONDS

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"


def make_fetcher(api_key: str, sleep_fn=time.sleep, urlopen=urllib.request.urlopen):
    def fetch(query: str, year: int | None) -> dict:
        params = {"api_key": api_key, "query": query}
        if year is not None:
            params["primary_release_year"] = year
        url = f"{TMDB_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        try:
            with urlopen(url, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        finally:
            sleep_fn(REQUEST_DELAY_SECONDS)

    return fetch
