import io
import json
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

from catalog import config
from catalog.errors import ShopifyError
from catalog.shopify import api, reader

STORE = "p0wkgv-wy.myshopify.com"


class FakeResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body):
    return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(json.dumps(body).encode()))


def fake_urlopen(*responses):
    """Each call pops the next response; an exception instance is raised instead."""
    calls = []
    queue = list(responses)

    def urlopen(request, timeout=None):
        calls.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    return urlopen, calls


class TestRequestToken(unittest.TestCase):
    def test_client_credentials_grant(self):
        urlopen, calls = fake_urlopen({"access_token": "tok", "scope": "read_products", "expires_in": 86399})
        self.assertEqual(api.request_token(STORE, "cid", "secret", urlopen=urlopen), "tok")
        request = calls[0]
        self.assertEqual(request.full_url, f"https://{STORE}/admin/oauth/access_token")
        self.assertEqual(urllib.parse.parse_qs(request.data.decode()),
                         {"grant_type": ["client_credentials"], "client_id": ["cid"], "client_secret": ["secret"]})

    def test_app_not_installed_says_to_install_it(self):
        urlopen, _ = fake_urlopen(http_error(400, {"error": "app_not_installed"}))
        with self.assertRaises(ShopifyError) as ctx:
            api.request_token(STORE, "cid", "secret", urlopen=urlopen)
        self.assertIn("install", str(ctx.exception).lower())
        self.assertNotIn("secret", str(ctx.exception))  # never echo the secret

    def test_bad_credentials(self):
        urlopen, _ = fake_urlopen(http_error(401, {"error": "invalid_client"}))
        with self.assertRaises(ShopifyError) as ctx:
            api.request_token(STORE, "cid", "secret", urlopen=urlopen)
        self.assertIn("invalid_client", str(ctx.exception))


class TestExecutor(unittest.TestCase):
    def test_posts_the_query_file_with_the_token(self):
        urlopen, calls = fake_urlopen({"data": {"products": {}}})
        execute = api.make_executor(STORE, "tok", urlopen=urlopen, sleep=lambda s: None)
        payload = execute(STORE, reader.QUERY_PATH, {"cursor": None})
        self.assertEqual(payload, {"data": {"products": {}}})
        request = calls[0]
        self.assertEqual(request.full_url, f"https://{STORE}/admin/api/{config.SHOPIFY_API_VERSION}/graphql.json")
        self.assertEqual(request.get_header("X-shopify-access-token"), "tok")
        body = json.loads(request.data)
        self.assertEqual(body["variables"], {"cursor": None})
        self.assertIn("query CatalogProducts", body["query"])

    def test_retries_when_throttled(self):
        sleeps = []
        urlopen, calls = fake_urlopen(http_error(429, {"errors": "Throttled"}),
                                      {"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]},
                                      {"data": {"ok": True}})
        execute = api.make_executor(STORE, "tok", urlopen=urlopen, sleep=sleeps.append)
        self.assertEqual(execute(STORE, reader.QUERY_PATH, {}), {"data": {"ok": True}})
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(sleeps), 2)

    def test_gives_up_after_repeated_throttling(self):
        urlopen, _ = fake_urlopen(*[http_error(429, {"errors": "Throttled"})] * 10)
        execute = api.make_executor(STORE, "tok", urlopen=urlopen, sleep=lambda s: None)
        with self.assertRaises(ShopifyError):
            execute(STORE, reader.QUERY_PATH, {})

    def test_auth_failure_is_a_shopify_error(self):
        urlopen, _ = fake_urlopen(http_error(401, {"errors": "Invalid API key or access token"}))
        execute = api.make_executor(STORE, "tok", urlopen=urlopen, sleep=lambda s: None)
        with self.assertRaises(ShopifyError):
            execute(STORE, reader.QUERY_PATH, {})


class TestSourceChoice(unittest.TestCase):
    def env(self, values):
        return mock.patch.dict("os.environ", values, clear=True), mock.patch.object(config, "ENV_FILE",
                                                                                     Path("/nonexistent/.env"))

    def test_uses_the_admin_api_when_credentials_are_set(self):
        environ, env_file = self.env({"SHOPIFY_CLIENT_ID": "cid", "SHOPIFY_CLIENT_SECRET": "secret"})
        with environ, env_file, mock.patch.object(api, "request_token", return_value="tok") as token:
            execute, source = reader.default_executor(STORE)
        token.assert_called_once_with(STORE, "cid", "secret")
        self.assertEqual(source, "Admin API")
        self.assertIsNot(execute, reader.run_cli_query)

    def test_falls_back_to_the_cli_without_credentials(self):
        environ, env_file = self.env({})
        with environ, env_file:
            execute, source = reader.default_executor(STORE)
        self.assertIs(execute, reader.run_cli_query)
        self.assertEqual(source, "Shopify CLI")


if __name__ == "__main__":
    unittest.main()
