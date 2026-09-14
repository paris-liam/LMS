#!/usr/bin/env bash
# Creates the two customer metafield definitions the membership Flow
# automation writes to (see docs/superpowers/specs/2026-09-13-membership-system-design.md §4-5).
# Idempotent: re-running is safe — a "key is in use" userError is treated as OK.
#
# Usage:
#   ./scripts/create-membership-metafield-definitions.sh
#   SHOPIFY_STORE=other-store.myshopify.com ./scripts/create-membership-metafield-definitions.sh
#
# Auth: uses the Shopify CLI's own session (run `shopify store auth --store <store>
# --scopes write_metafield_definitions` once first if needed).

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"

QUERY='mutation CreateDef($definition: MetafieldDefinitionInput!) {
  metafieldDefinitionCreate(definition: $definition) {
    createdDefinition { id namespace key type { name } }
    userErrors { field message code }
  }
}'

DEFINITIONS=$(cat <<'JSON'
[
  { "name":"Libib patron barcode","namespace":"custom","key":"libib_barcode","ownerType":"CUSTOMER","type":"single_line_text_field","description":"Barcode returned by Libib POST /patrons when this member's patron record was created. Written by the membership Flow automation." },
  { "name":"Membership birthday","namespace":"custom","key":"birthday","ownerType":"CUSTOMER","type":"single_line_text_field","description":"Member birthday as typed at signup (format: MM/DD/YYYY, not validated as a date type). Powers the free birthday movie perk. Overwritten if the member signs up again." }
]
JSON
)

echo "Store: ${STORE}"
echo

echo "$DEFINITIONS" | jq -c '.[]' | while read -r DEF; do
  KEY=$(echo "$DEF" | jq -r '.key')
  VARS=$(jq -n --argjson d "$DEF" '{definition: $d}')
  RESP=$(shopify store execute --store "$STORE" --allow-mutations -j -q "$QUERY" -v "$VARS")

  ERR_MSG=$(echo "$RESP" | jq -r '.metafieldDefinitionCreate.userErrors[0].message // empty')
  ERR_CODE=$(echo "$RESP" | jq -r '.metafieldDefinitionCreate.userErrors[0].code // empty')

  if [[ -n "$ERR_MSG" && "$ERR_CODE" != "TAKEN" ]]; then
    echo "  ✗ custom.${KEY}: ${ERR_MSG}" >&2
    exit 1
  elif [[ -n "$ERR_MSG" ]]; then
    echo "  = custom.${KEY}: already exists, skipping"
  else
    echo "  ✓ custom.${KEY}: created"
  fi
done
