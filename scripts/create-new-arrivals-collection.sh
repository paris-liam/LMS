#!/usr/bin/env bash
# Creates the "New Arrivals" smart collection (handle: new-arrivals) that
# feeds the homepage New Arrivals rail. Membership is fully rule-driven —
# Category = Media > Videos AND tag = Rental AND tag = new-arrival — so a
# product enters/leaves automatically as the new-arrival tag is added/removed
# by the Shopify Flow set up in the admin runbook (Task 6).
# Idempotent: a "handle has already been taken" userError is treated as OK.
#
# Auth: uses the Shopify CLI's own authenticated session (run
# `shopify store auth --store <store> --scopes write_products` once first if
# you haven't already) — no admin token needs to be exported.
#
# Usage:
#   ./scripts/create-new-arrivals-collection.sh

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"

MUTATION='mutation Create($input: CollectionInput!) {
  collectionCreate(input: $input) { collection { id handle } userErrors { field message } }
}'
VARS=$(jq -n '{
  input: {
    title: "New Arrivals",
    handle: "new-arrivals",
    sortOrder: "CREATED_DESC",
    ruleSet: {
      appliedDisjunctively: false,
      rules: [
        { column: "PRODUCT_CATEGORY_ID", relation: "EQUALS", condition: "gid://shopify/TaxonomyCategory/me-7" },
        { column: "TAG", relation: "EQUALS", condition: "Rental" },
        { column: "TAG", relation: "EQUALS", condition: "new-arrival" }
      ]
    }
  }
}')
RESP=$(shopify store execute --store "$STORE" --allow-mutations -j -q "$MUTATION" -v "$VARS")
ERR=$(echo "$RESP" | jq -r '.collectionCreate.userErrors[0].message // empty')
if [[ -n "$ERR" ]]; then
  if echo "$ERR" | grep -qiE 'taken|already|in use'; then
    echo "= New Arrivals: exists (ok)"
  else
    echo "✗ New Arrivals: ${ERR}"; exit 1
  fi
else
  echo "✓ New Arrivals created → $(echo "$RESP" | jq -r '.collectionCreate.collection.handle')"
fi
