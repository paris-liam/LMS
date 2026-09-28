"""Paths, the default store, and secret lookup. Secrets never live in source."""

import os
from pathlib import Path

from catalog.errors import MissingEnvError

REPO_ROOT = Path(__file__).resolve().parents[1]

# CLAUDE.md: production is the working store until the major release.
DEFAULT_STORE = "p0wkgv-wy.myshopify.com"

RUNS_DIR = REPO_ROOT / "runs"
TMDB_CACHE_FILENAME = ".tmdb-cache.json"
PICKER_DIR = REPO_ROOT / "tools" / "review-picker"
LIBIB_SYNC_DIR = REPO_ROOT / "libib-sync"
# apply copies each run's import CSVs here (tracked) and publishes them, so a
# cloud session's CSVs reach the user through GitHub.
IMPORTS_DIR = REPO_ROOT / "imports"

ENV_TMDB_API_KEY = "TMDB_API_KEY"
ENV_LIBIB_EMAIL = "LIBIB_EMAIL"
ENV_LIBIB_PASSWORD = "LIBIB_PASSWORD"
# Dev Dashboard custom app (read-only scopes) installed on the store; the
# reader trades these for a 24-hour Admin API token. Without them it falls
# back to the Shopify CLI's stored login.
ENV_SHOPIFY_CLIENT_ID = "SHOPIFY_CLIENT_ID"
ENV_SHOPIFY_CLIENT_SECRET = "SHOPIFY_CLIENT_SECRET"
SHOPIFY_API_VERSION = "2026-07"


# Local secrets file (gitignored — see .env.example). An exported variable
# always wins over the file. Tests point ENV_FILE elsewhere so a developer's
# real .env never leaks into them.
ENV_FILE = REPO_ROOT / ".env"


def _read_env_file(path) -> dict:
    values = {}
    path = Path(path)
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def get_env(name: str, environ=None, env_file=None) -> str | None:
    """Like require_env, but None when the variable isn't set anywhere."""
    try:
        return require_env(name, environ, env_file)
    except MissingEnvError:
        return None


def require_env(name: str, environ=None, env_file=None) -> str:
    environ = os.environ if environ is None else environ
    value = (environ.get(name) or "").strip()
    if not value:
        value = (_read_env_file(ENV_FILE if env_file is None else env_file).get(name) or "").strip()
    if not value:
        raise MissingEnvError(f"{name} is not set. Add {name}=... to {ENV_FILE} or export it.")
    return value

# The hosted review picker (Vercel) deploys tools/review-picker from this
# branch, and /api/save-pick commits the client's picks to it.
PICKER_REL = "tools/review-picker"
PICKER_REMOTE = "origin"
PICKER_BRANCH = "main"
