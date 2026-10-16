import ast
import base64
import gzip
import importlib.util
import io
import json
import sys
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tests_rental_sync_fakes import FakeShop  # noqa: E402

from catalog.errors import SetupError, ShopifyError  # noqa: E402
from catalog.rental_sync.auth import COOKIE_NAME, new_session  # noqa: E402
from catalog.rental_sync.web import MAX_BODY_BYTES, ROUTES, Deps, make_handler, respond  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ENV = {"SYNC_PASSWORD": "pw", "SESSION_SECRET": "secret", "SHOPIFY_STORE": "lms-sandbox-lutsfahz.myshopify.com",
       "SHOPIFY_CLIENT_ID": "id", "SHOPIFY_CLIENT_SECRET": "cs", "TMDB_API_KEY": "tk"}
NOW = 1_800_000_000.0
BARCODES = ("id,item_type,barcode,title,collection,tags,call_number,created\n"
            'a1,movie,2010000000014,Jaws,Rental Library,"vhs, horror",,2026-10-14\n')
LIBRARY = "id,item_type,title,collection,description,call_number\na1,movie,Jaws,Rental Library,A shark.,\n"


def upload(text):
    return base64.b64encode(gzip.compress(text.encode())).decode()


class Harness:
    def __init__(self, shop=None, env=None, fetch_results=None):
        self.shop = shop or FakeShop()
        self.sleeps, self.logs = [], []
        self.deps = Deps(env=dict(ENV if env is None else env), shop=lambda env: self.shop,
                         fetcher=lambda env: (lambda q, y: {"results": fetch_results or []}),
                         now=lambda: NOW, sleep=self.sleeps.append, log=self.logs.append)

    def call(self, route, body=None, method=None, cookie=True):
        headers = {"cookie": f"{COOKIE_NAME}={new_session('secret', NOW)}"} if cookie else {}
        method = method or ("GET" if route == "status" else "POST")
        raw = json.dumps(body).encode() if isinstance(body, (dict, list)) else (body or b"")
        status, out_headers, out = respond(route, method, headers, raw, self.deps)
        return status, dict(out_headers), json.loads(out)


class TestGuards(unittest.TestCase):
    def test_missing_setting_is_setup_error(self):
        status, _, body = Harness(env={**ENV, "SESSION_SECRET": ""}).call("status")
        self.assertEqual((status, body["error"]["kind"]), (500, "setup"))
        self.assertIn("SESSION_SECRET", body["error"]["detail"])

    def test_unknown_route_and_wrong_method(self):
        h = Harness()
        self.assertEqual(h.call("nope")[0], 404)
        self.assertEqual(h.call("prepare", method="GET")[0], 405)

    def test_every_route_but_login_needs_a_session(self):
        h = Harness()
        for route in ("status", "prepare", "posters", "create", "finish"):
            status, _, body = h.call(route, {}, cookie=False)
            self.assertEqual((status, body["error"]["kind"]), (401, "auth"), route)

    def test_invalid_json_is_input_error(self):
        status, _, body = Harness().call("prepare", b"{not json")
        self.assertEqual((status, body["error"]["kind"]), (400, "input"))


class TestLogin(unittest.TestCase):
    def test_wrong_password_waits(self):
        h = Harness()
        status, headers, _ = h.call("login", {"password": "nope"}, cookie=False)
        self.assertEqual(status, 401)
        self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(h.sleeps, [2])

    def test_right_password_sets_cookie(self):
        status, headers, body = Harness().call("login", {"password": "pw"}, cookie=False)
        self.assertEqual((status, body), (200, {"ok": True}))
        self.assertIn(f"{COOKIE_NAME}=", headers["Set-Cookie"])


class TestRoutes(unittest.TestCase):
    def test_status(self):
        status, headers, body = Harness(shop=FakeShop(last={"created": 3})).call("status")
        self.assertEqual((status, body), (200, {"store": "lms-sandbox-lutsfahz.myshopify.com", "last_run": {"created": 3}}))
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_status_when_shopify_is_down(self):
        class Down(FakeShop):
            def last_run(self):
                raise ShopifyError("could not reach Shopify: TimeoutError")

        status, _, body = Harness(shop=Down()).call("status")
        self.assertEqual((status, body["error"]["kind"]), (503, "shopify"))

    def test_prepare(self):
        status, _, body = Harness().call("prepare", {"barcodes": upload(BARCODES), "library": upload(LIBRARY)})
        self.assertEqual(status, 200)
        self.assertEqual([c["title"] for c in body["ready"]], ["Jaws"])
        self.assertIn("vhs", body["vocabulary"]["formats"])

    def test_prepare_bad_upload_and_swapped(self):
        h = Harness()
        self.assertEqual(h.call("prepare", {"barcodes": "%%", "library": upload(LIBRARY)})[0], 400)
        status, _, body = h.call("prepare", {"barcodes": upload(LIBRARY), "library": upload(BARCODES)})
        self.assertEqual(status, 400)
        self.assertIn("swapped", body["error"]["message"])

    def test_prepare_when_shopify_is_down(self):
        h = Harness(shop=FakeShop(barcodes_error=ShopifyError("could not reach store")))
        status, _, body = h.call("prepare", {"barcodes": upload(BARCODES), "library": upload(LIBRARY)})
        self.assertEqual((status, body["error"]["kind"]), (503, "shopify"))
        self.assertIn("Nothing has been changed", body["error"]["message"])

    def test_posters(self):
        copy = {"libib": {"barcode": "2010000000014", "title": "Jaws", "tags": "vhs, horror",
                          "description": "", "created": ""}}
        status, _, body = Harness().call("posters", {"copies": [copy]})
        self.assertEqual((status, body["posters"][0]["kind"]), (200, "none"))
        self.assertEqual(Harness().call("posters", {"copies": [copy] * 6})[0], 400)

    def test_create(self):
        h = Harness()
        item = {"barcode": "2010000000014", "title": "Jaws", "tags": "vhs, horror", "description": "", "created": ""}
        status, _, body = h.call("create", {"item": item, "poster": None})
        self.assertEqual((status, body["status"]), (200, "created"))
        self.assertTrue(any("2010000000014" in line and "created" in line for line in h.logs))
        bad = h.call("create", {"item": item, "poster": {"url": "http://x/p.jpg", "alt": ""}})
        self.assertEqual(bad[0], 400)

    def test_create_setup_error(self):
        h = Harness(shop=FakeShop(location_error=SetupError("found 2 locations")))
        item = {"barcode": "2010000000014", "title": "Jaws", "tags": "vhs, horror", "description": "", "created": ""}
        status, _, body = h.call("create", {"item": item, "poster": None})
        self.assertEqual((status, body["error"]["kind"]), (500, "setup"))
        self.assertIn("contact Liam", body["error"]["message"])

    def test_finish(self):
        h = Harness()
        status, _, body = h.call("finish", {"created": 2, "skipped": 1, "failed": 0, "set_aside": 3})
        self.assertEqual(status, 200)
        self.assertEqual(h.shop.saved[0], {"created": 2, "skipped": 1, "failed": 0, "set_aside": 3,
                                           "finished_at": "2027-01-15T08:00:00+00:00"})
        self.assertEqual(h.call("finish", {"created": "lots"})[0], 400)

    def test_unexpected_error_is_logged_not_leaked(self):
        class Broken(FakeShop):
            def last_run(self):
                raise ZeroDivisionError("boom")
        h = Harness(shop=Broken())
        status, _, body = h.call("status")
        self.assertEqual((status, body["error"]["kind"]), (500, "setup"))
        self.assertTrue(any("ZeroDivisionError" in line for line in h.logs))


class _Socket:
    def __init__(self, raw):
        self.raw, self.out = raw, io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        return io.BytesIO(self.raw) if "r" in mode else _KeepOpen(self.out)

    def sendall(self, data):
        self.out.write(data)


class _KeepOpen(io.RawIOBase):
    def __init__(self, sink):
        self.sink = sink

    def writable(self):
        return True

    def write(self, data):
        return self.sink.write(data)


def serve(harness, request_head, body=b"", route="status"):
    """Drive the real BaseHTTPRequestHandler over an in-memory socket."""
    sock = _Socket(request_head.encode() + b"\r\n\r\n" + body)
    make_handler(route, lambda: harness.deps)(sock, ("127.0.0.1", 0), None)
    head, _, payload = sock.out.getvalue().partition(b"\r\n\r\n")
    return int(head.split()[1]), json.loads(payload)


class TestHandler(unittest.TestCase):
    def test_oversized_body_is_413(self):
        status, body = serve(Harness(), f"POST /x HTTP/1.1\r\nContent-Length: {MAX_BODY_BYTES + 1}", route="prepare")
        self.assertEqual((status, body["error"]["kind"]), (413, "input"))

    def test_bad_content_length_is_400(self):
        for bad in ("abc", "-5"):
            status, body = serve(Harness(), f"POST /x HTTP/1.1\r\nContent-Length: {bad}", route="prepare")
            self.assertEqual((status, body["error"]["kind"]), (400, "input"), bad)
            self.assertIn("wasn't readable", body["error"]["message"])

    def test_cookie_header_reaches_the_session_check(self):
        cookie = f"{COOKIE_NAME}={new_session('secret', NOW)}"
        status, body = serve(Harness(), f"GET /x HTTP/1.1\r\nCookie: {cookie}")
        self.assertEqual((status, body["store"]), (200, "lms-sandbox-lutsfahz.myshopify.com"))
        self.assertEqual(serve(Harness(), "GET /x HTTP/1.1")[0], 401)


class TestEntryPoints(unittest.TestCase):
    def test_every_route_has_a_vercel_function(self):
        files = {p.stem for p in (REPO / "api" / "rental_sync").glob("*.py")}
        self.assertEqual(files, set(ROUTES))

    def test_entry_points_import_and_expose_a_handler(self):
        for route in ROUTES:
            path = REPO / "api" / "rental_sync" / f"{route}.py"
            spec = importlib.util.spec_from_file_location(f"api_rental_sync_{route}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertTrue(issubclass(module.handler, BaseHTTPRequestHandler), route)

    def test_entry_points_define_handler_as_a_class_statement(self):
        # Vercel's Python builder finds /api functions by reading the source for a
        # top-level `class handler` — it does not import the file, so an assignment
        # (`handler = make_handler(...)`) leaves the deploy with no functions at all.
        for route in ROUTES:
            tree = ast.parse((REPO / "api" / "rental_sync" / f"{route}.py").read_text(encoding="utf-8"))
            classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
            self.assertIn("handler", classes, route)


if __name__ == "__main__":
    unittest.main()
