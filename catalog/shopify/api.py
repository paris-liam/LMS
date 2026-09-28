"""Read Shopify through the Admin GraphQL API with a custom app's credentials.

The app (Dev Dashboard, installed on the store, read-only scopes) exchanges
its client ID + secret for a 24-hour access token (client credentials grant).
A fresh token is requested for every run and only ever held in memory.
Only queries are sent — the token has no write scopes anyway.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from catalog import config
from catalog.errors import ShopifyError

MAX_ATTEMPTS = 6
TIMEOUT_SECONDS = 30


def _error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")[:300]
    except Exception:
        return ""
    finally:
        exc.close()


def request_token(store: str, client_id: str, client_secret: str, urlopen=urllib.request.urlopen) -> str:
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": client_id,
                                   "client_secret": client_secret}).encode()
    request = urllib.request.Request(f"https://{store}/admin/oauth/access_token", data=body,
                                     headers={"Content-Type": "application/x-www-form-urlencoded",
                                              "Accept": "application/json"})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            token = json.loads(response.read()).get("access_token")
    except urllib.error.HTTPError as exc:
        detail = _error_body(exc)
        if "app_not_installed" in detail:
            raise ShopifyError(f"the Shopify app is not installed on {store} — install it from the Dev Dashboard "
                               f"(release a version with read_products, read_inventory, read_metaobjects)") from None
        raise ShopifyError(f"Shopify refused the app credentials for {store} (HTTP {exc.code}): {detail}") from None
    except urllib.error.URLError as exc:
        raise ShopifyError(f"could not reach {store} for an access token: {exc.reason}") from None
    if not token:
        raise ShopifyError(f"Shopify returned no access token for {store}")
    return token


def _throttled(payload: dict) -> bool:
    return any((e.get("extensions") or {}).get("code") == "THROTTLED" for e in payload.get("errors") or []
               if isinstance(e, dict))


def make_executor(store: str, token: str, version: str = config.SHOPIFY_API_VERSION,
                  urlopen=urllib.request.urlopen, sleep=time.sleep):
    """An execute(store, query_path, variables) -> payload with the same shape
    as reader.run_cli_query, so read_products works with either."""
    url = f"https://{store}/admin/api/{version}/graphql.json"

    def execute(_store, query_path, variables: dict) -> dict:
        body = json.dumps({"query": query_path.read_text(encoding="utf-8"), "variables": variables}).encode()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            request = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json", "X-Shopify-Access-Token": token})
            try:
                with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                    payload = json.loads(response.read())
            except urllib.error.HTTPError as exc:
                detail = _error_body(exc)
                if exc.code in (429, 502, 503, 504) and attempt < MAX_ATTEMPTS:
                    sleep(2 ** attempt)
                    continue
                if exc.code in (401, 403):
                    raise ShopifyError(f"Shopify rejected the access token for {store} (HTTP {exc.code}): "
                                       f"{detail} — check the app's scopes and that it is installed") from None
                raise ShopifyError(f"Shopify API error from {store} (HTTP {exc.code}): {detail}") from None
            except urllib.error.URLError as exc:
                if attempt < MAX_ATTEMPTS:
                    sleep(2 ** attempt)
                    continue
                raise ShopifyError(f"could not reach {store}: {exc.reason}") from None
            if _throttled(payload) and attempt < MAX_ATTEMPTS:
                sleep(2 ** attempt)
                continue
            return payload
        raise ShopifyError(f"Shopify kept throttling requests to {store} after {MAX_ATTEMPTS} attempts")

    return execute
