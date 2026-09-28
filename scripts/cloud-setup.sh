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

python3 -m pip install --quiet --root-user-action=ignore playwright
python3 -m playwright install chromium

# Chromium's system libraries come from apt. Cloud images can ship extra PPA
# sources their network blocks (403 from ppa.launchpadcontent.net), which makes
# `apt-get update` — and so `playwright install-deps` — fail outright. On a
# failure, disable only those PPA sources and retry.
PY="$(command -v python3)"   # sudo may not find the same python3
SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"
if ! $SUDO "$PY" -m playwright install-deps chromium; then
  echo "install-deps failed; disabling blocked PPA sources and retrying"
  for f in /etc/apt/sources.list.d/*; do
    if [ -f "$f" ] && grep -q "ppa.launchpadcontent.net" "$f"; then
      $SUDO mv "$f" "$f.disabled"
      echo "  disabled $f"
    fi
  done
  $SUDO "$PY" -m playwright install-deps chromium
fi
echo "cloud setup done — next: python3 -m catalog libib check-login"
