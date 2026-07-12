#!/usr/bin/env bash
# Creates tag-driven automatic collections (dev store by default). Idempotent-ish:
# a duplicate-handle userError is treated as OK.
# Usage: same auth env as the other scripts. ./scripts/create-curation-collections.sh

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"
API_VERSION="2026-01"

if [[ -z "${SHOPIFY_ADMIN_TOKEN:-}" ]]; then
  if [[ -z "${SHOPIFY_CLIENT_ID:-}" || -z "${SHOPIFY_CLIENT_SECRET:-}" ]]; then
    echo "Set SHOPIFY_ADMIN_TOKEN, or SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET." >&2; exit 1
  fi
  TOKEN_RESPONSE=$(curl -sS "https://${STORE}/admin/oauth/access_token" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg id "$SHOPIFY_CLIENT_ID" --arg secret "$SHOPIFY_CLIENT_SECRET" \
      '{grant_type:"client_credentials", client_id:$id, client_secret:$secret}')")
  SHOPIFY_ADMIN_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token // empty')
  [[ -n "$SHOPIFY_ADMIN_TOKEN" ]] || { echo "Token exchange failed"; echo "$TOKEN_RESPONSE" | jq .; exit 1; }
fi

QUERY='mutation Create($input: CollectionInput!) {
  collectionCreate(input: $input) { collection { id handle } userErrors { field message } }
}'

# title | tag | handle
# An explicit deterministic handle is set so a re-run collides on a unique
# handle and returns a "handle has already been taken" userError (caught
# below as "exists (ok)"). Without it, collectionCreate would silently mint
# a suffixed duplicate (staff-picks-2) on re-run instead of being a no-op.
COLLECTIONS=$(cat <<'JSON'
[
  { "title":"Staff Picks",   "tag":"staff-pick", "handle":"staff-picks" },
  { "title":"Rare Finds",    "tag":"rare",       "handle":"rare-finds" },
  { "title":"Holiday Movies","tag":"holiday",    "handle":"holiday-movies" }
]
JSON
)

echo "$COLLECTIONS" | jq -c '.[]' | while read -r C; do
  TITLE=$(echo "$C" | jq -r '.title'); TAG=$(echo "$C" | jq -r '.tag'); HANDLE=$(echo "$C" | jq -r '.handle')
  INPUT=$(jq -n --arg t "$TITLE" --arg tag "$TAG" --arg h "$HANDLE" '{
    title:$t,
    handle:$h,
    ruleSet:{ appliedDisjunctively:false, rules:[{ column:"TAG", relation:"EQUALS", condition:$tag }] }
  }')
  RESP=$(curl -sS "https://${STORE}/admin/api/${API_VERSION}/graphql.json" \
    -H "Content-Type: application/json" -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
    -d "$(jq -n --arg q "$QUERY" --argjson i "$INPUT" '{query:$q, variables:{input:$i}}')")
  ERR=$(echo "$RESP" | jq -r '.data.collectionCreate.userErrors[0].message // empty')
  if [[ -n "$ERR" ]]; then
    if echo "$ERR" | grep -qiE 'taken|already|in use'; then echo "  = ${TITLE}: exists (ok)";
    else echo "  ✗ ${TITLE}: ${ERR}"; exit 1; fi
  else
    echo "  ✓ ${TITLE} (tag='${TAG}') → $(echo "$RESP" | jq -r '.data.collectionCreate.collection.handle')"
  fi
done
echo "✓ Curation collections ready."
