#!/usr/bin/env bash
# Seeds one product with sample custom.* movie values + curation tags (dev store by default).
# Usage:
#   export SHOPIFY_ADMIN_TOKEN=shpat_...   # or CLIENT_ID/SECRET as in the definitions script
#   export PRODUCT_GID="gid://shopify/Product/1234567890"
#   ./scripts/seed-reference-movie.sh

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"
API_VERSION="2026-01"
: "${PRODUCT_GID:?Set PRODUCT_GID to a gid://shopify/Product/... value}"

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

# metafieldsSet — note list value is a JSON-array string; integers are strings.
SET_QUERY='mutation Set($m:[MetafieldsSetInput!]!){ metafieldsSet(metafields:$m){ metafields{ key } userErrors{ field message } } }'
METAFIELDS=$(jq -n --arg id "$PRODUCT_GID" '[
  {ownerId:$id, namespace:"custom", key:"director",        type:"single_line_text_field",      value:"Ridley Scott"},
  {ownerId:$id, namespace:"custom", key:"year",            type:"number_integer",              value:"1982"},
  {ownerId:$id, namespace:"custom", key:"decade",          type:"single_line_text_field",      value:"1980s"},
  {ownerId:$id, namespace:"custom", key:"country",         type:"single_line_text_field",      value:"United States"},
  {ownerId:$id, namespace:"custom", key:"runtime",         type:"number_integer",              value:"117"},
  {ownerId:$id, namespace:"custom", key:"genres",          type:"list.single_line_text_field", value:"[\"Sci-Fi\",\"Noir\"]"},
  {ownerId:$id, namespace:"custom", key:"format",          type:"single_line_text_field",      value:"Blu-ray"},
  {ownerId:$id, namespace:"custom", key:"label",           type:"single_line_text_field",      value:"Criterion"},
  {ownerId:$id, namespace:"custom", key:"media_condition", type:"single_line_text_field",      value:"Sealed / New"},
  {ownerId:$id, namespace:"custom", key:"staff_pick_note", type:"multi_line_text_field",       value:"A neon-drenched touchstone — our pick for the shelf."}
]')
RESP=$(curl -sS "https://${STORE}/admin/api/${API_VERSION}/graphql.json" \
  -H "Content-Type: application/json" -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
  -d "$(jq -n --arg q "$SET_QUERY" --argjson m "$METAFIELDS" '{query:$q, variables:{m:$m}}')")
echo "$RESP" | jq '.data.metafieldsSet.userErrors'
[[ "$(echo "$RESP" | jq -r '.data.metafieldsSet.userErrors | length')" == "0" ]] || { echo "metafieldsSet failed"; exit 1; }

# Curation tags
TAG_QUERY='mutation Tag($id:ID!,$tags:[String!]!){ tagsAdd(id:$id, tags:$tags){ userErrors{ message } } }'
curl -sS "https://${STORE}/admin/api/${API_VERSION}/graphql.json" \
  -H "Content-Type: application/json" -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
  -d "$(jq -n --arg q "$TAG_QUERY" --arg id "$PRODUCT_GID" '{query:$q, variables:{id:$id, tags:["rare","staff-pick"]}}')" \
  | jq '.data.tagsAdd.userErrors'

echo "✓ Seeded ${PRODUCT_GID}"
