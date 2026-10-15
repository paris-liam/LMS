"""One shared password, then a signed session cookie. The cookie carries only
its expiry and an HMAC of it; there is no server-side session store."""

import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie

COOKIE_NAME = "lms_rental_sync"
SESSION_SECONDS = 12 * 3600


def password_matches(given: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def _sign(secret: str, expiry: int) -> str:
    return hmac.new(secret.encode("utf-8"), str(expiry).encode("ascii"), hashlib.sha256).hexdigest()


def new_session(secret: str, now: float) -> str:
    expiry = int(now) + SESSION_SECONDS
    return f"{expiry}.{_sign(secret, expiry)}"


def session_cookie(value: str) -> str:
    return f"{COOKIE_NAME}={value}; Path=/; Max-Age={SESSION_SECONDS}; HttpOnly; Secure; SameSite=Strict"


def session_valid(cookie_header: str, secret: str, now: float) -> bool:
    jar = SimpleCookie()
    try:
        jar.load(cookie_header or "")
    except CookieError:
        return False
    morsel = jar.get(COOKIE_NAME)
    if morsel is None:
        return False
    expiry_text, _, signature = morsel.value.partition(".")
    if not expiry_text.isdigit():
        return False
    expiry = int(expiry_text)
    return expiry > now and hmac.compare_digest(signature, _sign(secret, expiry))
