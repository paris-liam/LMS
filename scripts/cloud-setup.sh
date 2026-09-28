#!/usr/bin/env bash
# Prepare a fresh cloud machine (e.g. a Claude Code on the web environment)
# to run the catalog pipeline, including the Libib browser fixer.
#
# Secrets are NOT set here — add them to the environment's secret settings:
#   TMDB_API_KEY, LIBIB_EMAIL, LIBIB_PASSWORD
#
# Then check Libib accepts a headless login from this machine:
#   python3 -m catalog libib check-login
set -euo pipefail

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    sys.exit(f"catalog needs Python 3.10+, found {sys.version.split()[0]}")
print(f"python {sys.version.split()[0]} ok")
PY

python3 -m pip install --quiet playwright
python3 -m playwright install --with-deps chromium
echo "cloud setup done — next: python3 -m catalog libib check-login"
