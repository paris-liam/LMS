#!/usr/bin/env bash
# One-time backfill: tags every existing Rental product created in the last
# 7 days with `new-arrival`, so the New Arrivals collection (Task 2) is
# populated at launch. Going forward, the Shopify Flow from the admin
# runbook (Task 6) takes over tagging/untagging for new products. Safe to
# re-run — tagsAdd is idempotent (won't duplicate an existing tag).
#
# Auth: uses the Shopify CLI's own authenticated session (run
# `shopify store auth --store <store> --scopes write_products` once first if
# you haven't already) — no admin token needs to be exported.
#
# Usage:
#   ./scripts/backfill-new-arrival-tags.sh

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"

SINCE=$(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ)
echo "Backfilling new-arrival tag for tag:Rental products created since ${SINCE}..."

SEARCH_QUERY="tag:Rental AND created_at:>='${SINCE}'"
FIND='query Find($q: String!, $after: String) {
  products(first: 100, after: $after, query: $q) {
    edges { cursor node { id title } }
    pageInfo { hasNextPage }
  }
}'
TAG_ADD='mutation Tag($id: ID!, $tags: [String!]!) {
  tagsAdd(id: $id, tags: $tags) { userErrors { field message } }
}'

AFTER="null"
TOTAL=0
while :; do
  VARS=$(jq -n --arg q "$SEARCH_QUERY" --argjson after "$AFTER" '{q: $q, after: $after}')
  RESP=$(shopify store execute --store "$STORE" -j -q "$FIND" -v "$VARS")
  EDGES=$(echo "$RESP" | jq -c '.products.edges[]')
  if [[ -z "$EDGES" ]]; then break; fi

  while IFS= read -r EDGE; do
    PRODUCT_ID=$(echo "$EDGE" | jq -r '.node.id')
    TITLE=$(echo "$EDGE" | jq -r '.node.title')
    TAG_VARS=$(jq -n --arg id "$PRODUCT_ID" '{id: $id, tags: ["new-arrival"]}')
    TAG_RESP=$(shopify store execute --store "$STORE" --allow-mutations -j -q "$TAG_ADD" -v "$TAG_VARS")
    TAG_ERR=$(echo "$TAG_RESP" | jq -r '.tagsAdd.userErrors[0].message // empty')
    if [[ -n "$TAG_ERR" ]]; then
      echo "  ✗ ${TITLE}: ${TAG_ERR}"
    else
      TOTAL=$((TOTAL + 1))
      echo "  ✓ ${TITLE} tagged new-arrival"
    fi
  done <<< "$EDGES"

  HAS_NEXT=$(echo "$RESP" | jq -r '.products.pageInfo.hasNextPage')
  if [[ "$HAS_NEXT" != "true" ]]; then break; fi
  LAST_CURSOR=$(echo "$RESP" | jq -r '.products.edges[-1].cursor')
  AFTER=$(jq -n --arg c "$LAST_CURSOR" '$c')
done

echo "✓ Backfill complete: ${TOTAL} product(s) tagged new-arrival."
