"""HTTP layer for the rental sync app's Vercel functions.

Every route goes through respond(), which the tests call directly;
make_handler() adapts it to the BaseHTTPRequestHandler class Vercel's Python
runtime looks for. Messages are written for the client; technical detail goes
in "detail" (shown behind "Show details") and the function log.
"""

import json
import os
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from typing import Callable

from catalog.errors import CatalogError, InputShapeError, SetupError, ShopifyError
from catalog.rental_sync.auth import new_session, password_matches, session_cookie, session_valid
from catalog.rental_sync.create import create_item
from catalog.rental_sync.matches import attach_matches
from catalog.rental_sync.posters import lookup_poster
from catalog.rental_sync.prepare import decode_upload, load_uploads, prepare
from catalog.rental_sync.transform import LIBIB_FIELDS, transform, vocabulary

REQUIRED_SETTINGS = ("SYNC_PASSWORD", "SESSION_SECRET", "SHOPIFY_STORE", "SHOPIFY_CLIENT_ID",
                     "SHOPIFY_CLIENT_SECRET", "TMDB_API_KEY")
MAX_BODY_BYTES = 4 * 1024 * 1024
POSTER_BATCH_MAX = 5
FAILED_LOGIN_DELAY_SECONDS = 2
SETUP_MESSAGE = "Something's wrong with the app setup — contact Liam."
SHOPIFY_MESSAGE = "Shopify didn't respond — try again in a few minutes. Nothing has been changed."


@dataclass
class Deps:
    env: dict
    shop: Callable
    fetcher: Callable
    now: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    log: Callable[[str], None] = field(default=print)


def default_deps() -> Deps:
    from catalog.rental_sync.shopify import shop_from_env
    from catalog.tmdb.client import make_fetcher
    return Deps(env=dict(os.environ), shop=shop_from_env, fetcher=lambda env: make_fetcher(env["TMDB_API_KEY"]))


Response = tuple[int, list[tuple[str, str]], bytes]


def _json(status: int, payload: dict, extra_headers=()) -> Response:
    headers = [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store"),
               *extra_headers]
    return status, headers, json.dumps(payload).encode("utf-8")


def _error(status: int, kind: str, message: str, detail: str = "") -> Response:
    return _json(status, {"error": {"kind": kind, "message": message, "detail": detail}})


def _text(payload: dict, key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _item(raw) -> dict:
    if not isinstance(raw, dict):
        raise InputShapeError("That request was missing the Libib copy — reload the page and start again.")
    return {k: str(raw.get(k) or "") for k in LIBIB_FIELDS}


def _login(payload: dict, deps: Deps) -> Response:
    if password_matches(_text(payload, "password"), deps.env["SYNC_PASSWORD"]):
        cookie = session_cookie(new_session(deps.env["SESSION_SECRET"], deps.now()))
        return _json(200, {"ok": True}, [("Set-Cookie", cookie)])
    deps.sleep(FAILED_LOGIN_DELAY_SECONDS)
    return _error(401, "auth", "That password isn't right.")


def _status(payload: dict, deps: Deps) -> Response:
    shop = deps.shop(deps.env)
    return _json(200, {"store": shop.store, "last_run": shop.last_run()})


def _prepare(payload: dict, deps: Deps) -> Response:
    barcodes = decode_upload(_text(payload, "barcodes"), "Barcodes export")
    library = decode_upload(_text(payload, "library"), "Library export")
    items = load_uploads(barcodes, library)
    shop = deps.shop(deps.env)
    result = attach_matches(prepare(items, shop.new_flow_barcodes()), shop, shop.store)
    deps.log(f"prepare: {len(result['ready'])} ready, {len(result['set_aside'])} set aside, "
             f"{result['already_in_shopify']} already in Shopify")
    return _json(200, {**result, "vocabulary": vocabulary()})


def _posters(payload: dict, deps: Deps) -> Response:
    copies = payload.get("copies")
    if not isinstance(copies, list) or not 1 <= len(copies) <= POSTER_BATCH_MAX:
        raise InputShapeError(f"Send between 1 and {POSTER_BATCH_MAX} copies at a time.")
    fetch = deps.fetcher(deps.env)
    copies = [transform(_item(c.get("libib") if isinstance(c, dict) else None)) for c in copies]
    return _json(200, {"posters": [lookup_poster(copy, fetch) for copy in copies]})


def _create(payload: dict, deps: Deps) -> Response:
    item = _item(payload.get("item"))
    poster = payload.get("poster")
    if poster is not None:
        url = str((poster or {}).get("url") or "").strip() if isinstance(poster, dict) else ""
        if not url.startswith("https://"):
            raise InputShapeError("Poster links must start with https://")
        poster = {"url": url, "alt": str(poster.get("alt") or "")}
    result = create_item(deps.shop(deps.env), [item], poster, sleep=deps.sleep)
    deps.log(f"create {result['barcode']} {result['status']} {result['title']!r} {result['message']}".rstrip())
    return _json(200, result)


def _finish(payload: dict, deps: Deps) -> Response:
    try:
        counts = {k: int(payload.get(k) or 0) for k in ("created", "skipped", "failed", "set_aside")}
    except (TypeError, ValueError):
        raise InputShapeError("The run summary was malformed.") from None
    summary = {**counts, "finished_at": datetime.fromtimestamp(deps.now(), timezone.utc).isoformat(timespec="seconds")}
    deps.shop(deps.env).save_last_run(summary)
    return _json(200, {"last_run": summary})


ROUTES = {"login": _login, "status": _status, "prepare": _prepare, "posters": _posters,
          "create": _create, "finish": _finish}


def respond(route: str, method: str, headers: dict, body: bytes, deps: Deps) -> Response:
    try:
        missing = [name for name in REQUIRED_SETTINGS if not (deps.env.get(name) or "").strip()]
        if missing:
            raise SetupError(f"missing setting(s): {', '.join(missing)}")
        handler = ROUTES.get(route)
        if handler is None:
            return _error(404, "input", "Not found.")
        if method != ("GET" if route == "status" else "POST"):
            return _error(405, "input", "Method not allowed.")
        if route != "login" and not session_valid(headers.get("cookie", ""), deps.env["SESSION_SECRET"], deps.now()):
            return _error(401, "auth", "Please log in again.")
        payload = {}
        if method == "POST":
            try:
                payload = json.loads(body or b"{}")
            except ValueError:
                raise InputShapeError("That request wasn't readable — reload the page and try again.") from None
            if not isinstance(payload, dict):
                raise InputShapeError("That request wasn't readable — reload the page and try again.")
        return handler(payload, deps)
    except InputShapeError as exc:
        return _error(400, "input", str(exc))
    except ShopifyError as exc:
        deps.log(f"{route}: Shopify error: {exc}")
        return _error(503, "shopify", SHOPIFY_MESSAGE, str(exc))
    except CatalogError as exc:  # SetupError, MissingEnvError, a rejected TMDB key
        deps.log(f"{route}: setup error: {exc}")
        return _error(500, "setup", SETUP_MESSAGE, str(exc))
    except Exception as exc:  # a bug: log it, don't leak a traceback to the page
        deps.log(f"{route}: unexpected error\n{traceback.format_exc()}")
        return _error(500, "setup", SETUP_MESSAGE, f"unexpected error: {type(exc).__name__}")


def make_handler(route: str, deps_factory=default_deps):
    class Handler(BaseHTTPRequestHandler):
        def _serve(self, method: str) -> None:
            try:
                length = int(self.headers.get("content-length") or 0)
            except ValueError:
                length = -1
            if length < 0:
                status, headers, body = _error(400, "input", "That request wasn't readable — reload the page and try again.")
            elif length > MAX_BODY_BYTES:
                status, headers, body = _error(413, "input", "That upload is too big — is it the right Libib export?")
            else:
                raw = self.rfile.read(length) if length else b""
                lowered = {k.lower(): v for k, v in self.headers.items()}
                status, headers, body = respond(route, method, lowered, raw, deps_factory())
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._serve("GET")

        def do_POST(self):
            self._serve("POST")

        def log_message(self, *args):
            pass  # the default writes every request line to stderr; respond() logs what matters

    return Handler
