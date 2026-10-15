import unittest

from catalog.rental_sync.auth import (
    COOKIE_NAME, SESSION_SECONDS, new_session, password_matches, session_cookie, session_valid,
)

SECRET = "s3cret"


class TestAuth(unittest.TestCase):
    def test_password(self):
        self.assertTrue(password_matches("hunter2", "hunter2"))
        self.assertFalse(password_matches("hunter3", "hunter2"))
        self.assertFalse(password_matches("", ""))

    def test_session_round_trip(self):
        value = new_session(SECRET, 1000)
        self.assertTrue(session_valid(f"other=1; {COOKIE_NAME}={value}", SECRET, 1001))

    def test_expired(self):
        value = new_session(SECRET, 1000)
        self.assertFalse(session_valid(f"{COOKIE_NAME}={value}", SECRET, 1000 + SESSION_SECONDS + 1))

    def test_tampered_or_wrong_secret(self):
        expiry, _, sig = new_session(SECRET, 1000).partition(".")
        self.assertFalse(session_valid(f"{COOKIE_NAME}={int(expiry) + 999}.{sig}", SECRET, 1001))
        self.assertFalse(session_valid(f"{COOKIE_NAME}={expiry}.{sig}", "other", 1001))
        self.assertFalse(session_valid(f"{COOKIE_NAME}=garbage", SECRET, 1001))
        self.assertFalse(session_valid("", SECRET, 1001))
        self.assertFalse(session_valid('bad"cookie', SECRET, 1001))

    def test_cookie_attributes(self):
        header = session_cookie("v")
        for part in (f"{COOKIE_NAME}=v", "Path=/", f"Max-Age={SESSION_SECONDS}", "HttpOnly", "Secure", "SameSite=Strict"):
            self.assertIn(part, header)


if __name__ == "__main__":
    unittest.main()
