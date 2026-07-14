#!/usr/bin/env bash
# Creates the movie product metafield definitions (custom.* namespace, dev store by default).
# Idempotent: re-running is safe — a "key is in use / already taken" userError is treated as OK.
#
# Usage (client credentials — exchanges ID+secret for a 24h automation token):
#   export SHOPIFY_CLIENT_ID=...
#   export SHOPIFY_CLIENT_SECRET=...
#   ./scripts/create-movie-metafield-definitions.sh
#
# Or with a pre-minted token:
#   export SHOPIFY_ADMIN_TOKEN=shpat_...
#   ./scripts/create-movie-metafield-definitions.sh
#
# The app must be installed on the store with the write_metafield_definitions scope.

set -euo pipefail

# Defaults to the dev store; override only when explicitly targeting production.
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"
API_VERSION="2026-01"

if [[ -z "${SHOPIFY_ADMIN_TOKEN:-}" ]]; then
  if [[ -z "${SHOPIFY_CLIENT_ID:-}" || -z "${SHOPIFY_CLIENT_SECRET:-}" ]]; then
    echo "Set either SHOPIFY_ADMIN_TOKEN, or SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET." >&2
    exit 1
  fi
  echo "Exchanging client credentials for an access token…"
  TOKEN_RESPONSE=$(curl -sS "https://${STORE}/admin/oauth/access_token" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg id "$SHOPIFY_CLIENT_ID" --arg secret "$SHOPIFY_CLIENT_SECRET" \
      '{grant_type: "client_credentials", client_id: $id, client_secret: $secret}')")
  SHOPIFY_ADMIN_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token // empty')
  if [[ -z "$SHOPIFY_ADMIN_TOKEN" ]]; then
    echo "Token exchange failed:" >&2
    echo "$TOKEN_RESPONSE" | jq . >&2
    exit 1
  fi
  echo "✓ Got access token."
fi

QUERY='mutation CreateDef($definition: MetafieldDefinitionInput!) {
  metafieldDefinitionCreate(definition: $definition) {
    createdDefinition { id namespace key type { name } }
    userErrors { field message code }
  }
}'

# All definitions. Choice lists are embedded as an escaped JSON string in the
# "choices" validation. Every field is pinned and storefront-readable.
# NOTE: Label/Distributor is intentionally NOT a metafield — it is modelled as
# prefixed product tags (label-*). Genre IS a metafield (custom.genres, dropdown +
# native storefront facet). See the client guide.
DEFINITIONS=$(cat <<'JSON'
[
  { "name":"Director","namespace":"custom","key":"director","ownerType":"PRODUCT","type":"single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Film director (display only)" },
  { "name":"Year","namespace":"custom","key":"year","ownerType":"PRODUCT","type":"number_integer","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Release year; drives the Decade facet" },
  { "name":"Decade","namespace":"custom","key":"decade","ownerType":"PRODUCT","type":"single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Era bucket used as a storefront facet","validations":[{"name":"choices","value":"[\"Pre-1950\",\"1950s\",\"1960s\",\"1970s\",\"1980s\",\"1990s\",\"2000s\",\"2010s\",\"2020s\"]"}] },
  { "name":"Country","namespace":"custom","key":"country","ownerType":"PRODUCT","type":"single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Country of origin (single value for v1)" },
  { "name":"Runtime (min)","namespace":"custom","key":"runtime","ownerType":"PRODUCT","type":"number_integer","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Runtime in minutes; display as e.g. 142 min" },
  { "name":"Genres","namespace":"custom","key":"genres","ownerType":"PRODUCT","type":"list.single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"One or more genres; storefront facet","validations":[{"name":"choices","value":"[\"Action\",\"Adventure\",\"Animation\",\"Comedy\",\"Crime\",\"Cult\",\"Documentary\",\"Drama\",\"Fantasy\",\"Horror\",\"Musical\",\"Mystery\",\"Noir\",\"Romance\",\"Sci-Fi\",\"Thriller\",\"War\",\"Western\"]"}] },
  { "name":"Format","namespace":"custom","key":"format","ownerType":"PRODUCT","type":"single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Disc format; storefront facet","validations":[{"name":"choices","value":"[\"Blu-ray\",\"DVD\",\"4K UHD\",\"VHS\"]"}] },
  { "name":"Media condition","namespace":"custom","key":"media_condition","ownerType":"PRODUCT","type":"single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"RETAIL new-sealed stock only. Serialized rental/resale copies use Supercycle's per-item condition.","validations":[{"name":"choices","value":"[\"Sealed / New\",\"Like New\",\"Good\",\"Fair\"]"}] },
  { "name":"Staff pick note","namespace":"custom","key":"staff_pick_note","ownerType":"PRODUCT","type":"multi_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Staff blurb shown on card/PDP. Pair with the 'staff-pick' tag. NOT the same as the staff_pick metaobject." }
]
JSON
)

echo "$DEFINITIONS" | jq -c '.[]' | while read -r DEF; do
  KEY=$(echo "$DEF" | jq -r '.key')
  PAYLOAD=$(jq -n --arg q "$QUERY" --argjson d "$DEF" '{query:$q, variables:{definition:$d}}')
  RESP=$(curl -sS "https://${STORE}/admin/api/${API_VERSION}/graphql.json" \
    -H "Content-Type: application/json" \
    -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
    -d "$PAYLOAD")

  if echo "$RESP" | jq -e '.errors' >/dev/null 2>&1; then
    echo "  ✗ custom.${KEY}: transport/GraphQL error:"; echo "$RESP" | jq -c '.errors'
    exit 1
  fi
  ERR_MSG=$(echo "$RESP" | jq -r '.data.metafieldDefinitionCreate.userErrors[0].message // empty')
  if [[ -n "$ERR_MSG" ]]; then
    if echo "$ERR_MSG" | grep -qiE 'in use|already|taken'; then
      echo "  = custom.${KEY}: already exists (ok)"
    else
      echo "  ✗ custom.${KEY}: ${ERR_MSG}"; exit 1
    fi
  else
    echo "  ✓ custom.${KEY} created"
  fi
done

echo
echo "✓ Movie metafield definitions ready under the custom namespace."
echo "  Review/pin order in Admin → Settings → Custom data → Products."
