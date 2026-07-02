#!/usr/bin/env bash
# Creates the `staff_pick` metaobject definition (dev store by default).
# The type handle and field keys must match what
# theme/lms-redesign/sections/lms-staff-picks.liquid reads:
#   shop.metaobjects.staff_pick.values → pick.product / pick.quote / pick.staff_name
#
# Usage (client credentials — exchanges ID+secret for a 24h automation token):
#   export SHOPIFY_CLIENT_ID=...
#   export SHOPIFY_CLIENT_SECRET=...
#   ./scripts/create-staff-pick-metaobject.sh
#
# Or with a pre-minted token:
#   export SHOPIFY_ADMIN_TOKEN=shpat_...
#   ./scripts/create-staff-pick-metaobject.sh
#
# The app must be installed on the store with the
# write_metaobject_definitions access scope.

set -euo pipefail

# Defaults to the dev store; override only when explicitly targeting production:
#   SHOPIFY_STORE=p0wkgv-wy.myshopify.com ./scripts/create-staff-pick-metaobject.sh
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
  echo "✓ Got access token (expires in $(echo "$TOKEN_RESPONSE" | jq -r '.expires_in // "?"')s)"
fi

read -r -d '' QUERY <<'GRAPHQL' || true
mutation CreateStaffPickDefinition($definition: MetaobjectDefinitionCreateInput!) {
  metaobjectDefinitionCreate(definition: $definition) {
    metaobjectDefinition {
      id
      type
      name
      access { storefront }
      fieldDefinitions { key name type { name } }
    }
    userErrors { field message code }
  }
}
GRAPHQL

read -r -d '' VARIABLES <<'JSON' || true
{
  "definition": {
    "type": "staff_pick",
    "name": "Staff pick",
    "displayNameKey": "staff_name",
    "access": { "storefront": "PUBLIC_READ" },
    "capabilities": { "publishable": { "enabled": true } },
    "fieldDefinitions": [
      {
        "key": "product",
        "name": "Product",
        "type": "product_reference",
        "required": true,
        "description": "Poster, title, and link on the storefront come from this product"
      },
      {
        "key": "quote",
        "name": "Quote",
        "type": "multi_line_text_field",
        "description": "The shelf note, shown in quotes under the poster"
      },
      {
        "key": "staff_name",
        "name": "Staff name",
        "type": "single_line_text_field",
        "description": "Renders as \"— Picked by <name>\""
      }
    ]
  }
}
JSON

PAYLOAD=$(jq -n --arg q "$QUERY" --argjson v "$VARIABLES" '{query: $q, variables: $v}')

RESPONSE=$(curl -sS "https://${STORE}/admin/api/${API_VERSION}/graphql.json" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
  -d "$PAYLOAD")

echo "$RESPONSE" | jq .

ERRORS=$(echo "$RESPONSE" | jq -r '.data.metaobjectDefinitionCreate.userErrors // [] | length')
if [[ "$ERRORS" != "0" ]] || echo "$RESPONSE" | jq -e '.errors' >/dev/null; then
  echo "Definition NOT created — see errors above." >&2
  exit 1
fi

echo
echo "✓ staff_pick metaobject definition created with storefront access enabled."
echo "  Add entries in Admin → Content → Metaobjects → Staff pick."
