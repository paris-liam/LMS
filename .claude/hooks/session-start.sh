#!/bin/bash
# Trust the Claude Code on the web agent-proxy CA in Chromium's NSS store, so
# Playwright-driven headless Chromium (e.g. `python3 -m catalog libib check-login`)
# can verify HTTPS through the proxy instead of failing with
# ERR_CERT_AUTHORITY_INVALID. Web sessions only; idempotent.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

CA=/root/.ccr/agent-proxy-ca.crt
NSSDB="$HOME/.pki/nssdb"

if [ ! -f "$CA" ]; then
  exit 0
fi

if ! command -v certutil >/dev/null 2>&1; then
  apt-get install -y libnss3-tools >/dev/null 2>&1 \
    || { apt-get update >/dev/null 2>&1 && apt-get install -y libnss3-tools >/dev/null 2>&1; }
fi

mkdir -p "$NSSDB"
if ! certutil -d "sql:$NSSDB" -L >/dev/null 2>&1; then
  certutil -d "sql:$NSSDB" -N --empty-password
fi
if ! certutil -d "sql:$NSSDB" -L -n ccr-agent-proxy >/dev/null 2>&1; then
  certutil -d "sql:$NSSDB" -A -t "C,," -n ccr-agent-proxy -i "$CA"
fi
