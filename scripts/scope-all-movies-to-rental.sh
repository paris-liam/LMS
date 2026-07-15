#!/usr/bin/env bash
# Adds a "tag = Rental" rule to the existing "All Movies" smart collection
# (handle: all-movies), which already powers the hero's "Browse the shelves"
# button and the shop-all/search page. Re-running is safe: it always sets
# the ruleset to the same two rules (replace, not append).
#
# Auth: uses the Shopify CLI's own authenticated session (run
# `shopify store auth --store <store> --scopes write_products` once first if
# you haven't already) — no admin token needs to be exported.
#
# Usage:
#   ./scripts/scope-all-movies-to-rental.sh

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"

echo "Looking up 'all-movies' collection id..."
LOOKUP_QUERY='query { collectionByHandle(handle: "all-movies") { id ruleSet { rules { column relation condition } } } }'
LOOKUP_RESP=$(shopify store execute --store "$STORE" -j -q "$LOOKUP_QUERY")
COLLECTION_ID=$(echo "$LOOKUP_RESP" | jq -r '.collectionByHandle.id // empty')
if [[ -z "$COLLECTION_ID" ]]; then
  echo "✗ Could not find collection with handle 'all-movies':"; echo "$LOOKUP_RESP" | jq .; exit 1
fi
echo "  found: ${COLLECTION_ID}"

MUTATION='mutation UpdateRuleSet($input: CollectionInput!) {
  collectionUpdate(input: $input) {
    collection { id handle ruleSet { appliedDisjunctively rules { column relation condition } } }
    userErrors { field message }
  }
}'
VARS=$(jq -n --arg id "$COLLECTION_ID" '{
  input: {
    id: $id,
    ruleSet: {
      appliedDisjunctively: false,
      rules: [
        { column: "PRODUCT_CATEGORY_ID", relation: "EQUALS", condition: "gid://shopify/TaxonomyCategory/me-7" },
        { column: "TAG", relation: "EQUALS", condition: "Rental" }
      ]
    }
  }
}')
RESP=$(shopify store execute --store "$STORE" --allow-mutations -j -q "$MUTATION" -v "$VARS")
ERR=$(echo "$RESP" | jq -r '.collectionUpdate.userErrors[0].message // empty')
if [[ -n "$ERR" ]]; then
  echo "✗ collectionUpdate failed: ${ERR}"; exit 1
fi
echo "✓ All Movies ruleset updated:"
echo "$RESP" | jq '.collectionUpdate.collection.ruleSet'
