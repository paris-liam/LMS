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

ENV_TMDB_API_KEY = "TMDB_API_KEY"
ENV_LIBIB_EMAIL = "LIBIB_EMAIL"
ENV_LIBIB_PASSWORD = "LIBIB_PASSWORD"


def require_env(name: str, environ=None) -> str:
    environ = os.environ if environ is None else environ
    value = (environ.get(name) or "").strip()
    if not value:
        raise MissingEnvError(f"{name} is not set. Export it first: export {name}=...")
    return value

# The hosted review picker (Vercel) deploys tools/review-picker from this
# branch, and /api/save-pick commits the client's picks to it.
PICKER_REL = "tools/review-picker"
PICKER_REMOTE = "origin"
PICKER_BRANCH = "main"
