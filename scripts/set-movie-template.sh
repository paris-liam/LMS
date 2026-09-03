#!/usr/bin/env bash
# Assigns the `movie` template suffix (templates/product.movie.json) to every
# movie product, so movies render on the read-only in-store PDP instead of the
# default product template.
#
# WHY THIS EXISTS: Shopify's product-CSV import has no template-suffix column,
# so imported movies land on the DEFAULT product template — which renders
# price + variant-picker + quantity + add-to-cart + buy-buttons. On a rental
# priced at 0 that is a $0.00 "Buy now" button, contradicting the in-store-only
# design and the Supercycle contract in CLAUDE.md. Re-run after every import.
#
# PREDICATE — vendor, not tags. Vendor carries the media format (VHS/DVD/
# Blu-Ray/4K/Laserdisc/Betamax), which is what makes a product a movie under the data model
# decided 2026-08-07. Tags are NOT safe here: `Rango Tote bag` is merch tagged
# `Floor Sale` (would wrongly get the movie template) and `Deja Vu` is a real
# movie carrying neither scoping tag (would be missed).
#
# Safe to re-run — products already on the target suffix are skipped, and the
# mutation is idempotent.
#
# DRY RUN BY DEFAULT. Unlike the other scripts here, this one's blast radius is
# the entire catalogue and it changes how every movie page renders, so it will
# not mutate anything unless you pass --apply.
#
# Auth: uses the Shopify CLI's own authenticated session (run
# `shopify store auth --store <store> --scopes write_products` once first if
# you haven't already) — no admin token needs to be exported.
#
# Usage:
#   ./scripts/set-movie-template.sh              # dry run, lists what would change
#   ./scripts/set-movie-template.sh --apply      # actually sets the suffix
#   SHOPIFY_STORE=p0wkgv-wy.myshopify.com ./scripts/set-movie-template.sh --apply

set -euo pipefail
STORE="${SHOPIFY_STORE:-p0wkgv-wy.myshopify.com}"
TEMPLATE_SUFFIX="movie"
TEMPLATE_FILE="templates/product.${TEMPLATE_SUFFIX}.json"

APPLY=false
if [[ "${1:-}" == "--apply" ]]; then
  APPLY=true
elif [[ -n "${1:-}" ]]; then
  echo "Unknown argument: $1 (expected --apply or nothing)" >&2
  exit 1
fi

echo "Store: ${STORE}"
$APPLY && echo "Mode:  APPLY (will modify products)" || echo "Mode:  DRY RUN (no changes; pass --apply to commit)"
echo

# --- Preflight: the live theme must actually contain the template ----------
# Setting a suffix whose template is missing breaks the product page, so this
# is a hard gate rather than a warning.
THEME_Q='query Theme($f: [String!]) {
  themes(first: 1, roles: [MAIN]) {
    nodes { id name files(filenames: $f, first: 1) { nodes { filename } } }
  }
}'
THEME_VARS=$(jq -n --arg f "$TEMPLATE_FILE" '{f: [$f]}')
THEME_RESP=$(shopify store execute --store "$STORE" -j -q "$THEME_Q" -v "$THEME_VARS")
THEME_NAME=$(echo "$THEME_RESP" | jq -r '.themes.nodes[0].name // empty')
HAS_TEMPLATE=$(echo "$THEME_RESP" | jq -r '.themes.nodes[0].files.nodes[0].filename // empty')

if [[ -z "$THEME_NAME" ]]; then
  echo "✗ Could not read the live theme from ${STORE}" >&2
  exit 1
fi
if [[ -z "$HAS_TEMPLATE" ]]; then
  echo "✗ Live theme '${THEME_NAME}' has no ${TEMPLATE_FILE}." >&2
  echo "  Push the theme before running this, or every movie page will break." >&2
  exit 1
fi
echo "✓ Live theme '${THEME_NAME}' has ${TEMPLATE_FILE}"
echo

# --- Find movies by vendor -------------------------------------------------
SEARCH_QUERY="vendor:VHS OR vendor:DVD OR vendor:'Blu-Ray' OR vendor:'BLU-RAY' OR vendor:4K OR vendor:'4k' OR vendor:'Dvd' OR vendor:Laserdisc OR vendor:Betamax"

FIND='query Find($q: String!, $after: String) {
  products(first: 100, after: $after, query: $q) {
    edges { cursor node { id title vendor templateSuffix } }
    pageInfo { hasNextPage }
  }
}'
SET_TEMPLATE='mutation SetTemplate($id: ID!, $suffix: String!) {
  productUpdate(product: { id: $id, templateSuffix: $suffix }) {
    product { id templateSuffix }
    userErrors { field message }
  }
}'

AFTER="null"
CHANGED=0
SKIPPED=0
FAILED=0

while :; do
  VARS=$(jq -n --arg q "$SEARCH_QUERY" --argjson after "$AFTER" '{q: $q, after: $after}')
  RESP=$(shopify store execute --store "$STORE" -j -q "$FIND" -v "$VARS")
  EDGES=$(echo "$RESP" | jq -c '.products.edges[]?')
  if [[ -z "$EDGES" ]]; then break; fi

  while IFS= read -r EDGE; do
    PRODUCT_ID=$(echo "$EDGE" | jq -r '.node.id')
    TITLE=$(echo "$EDGE" | jq -r '.node.title')
    VENDOR=$(echo "$EDGE" | jq -r '.node.vendor')
    CURRENT=$(echo "$EDGE" | jq -r '.node.templateSuffix // ""')

    if [[ "$CURRENT" == "$TEMPLATE_SUFFIX" ]]; then
      SKIPPED=$((SKIPPED + 1))
      continue
    fi

    if ! $APPLY; then
      CHANGED=$((CHANGED + 1))
      echo "  would set [${VENDOR}] ${TITLE}"
      continue
    fi

    SET_VARS=$(jq -n --arg id "$PRODUCT_ID" --arg suffix "$TEMPLATE_SUFFIX" '{id: $id, suffix: $suffix}')
    SET_RESP=$(shopify store execute --store "$STORE" --allow-mutations -j -q "$SET_TEMPLATE" -v "$SET_VARS")
    SET_ERR=$(echo "$SET_RESP" | jq -r '.productUpdate.userErrors[0].message // empty')
    if [[ -n "$SET_ERR" ]]; then
      FAILED=$((FAILED + 1))
      echo "  ✗ ${TITLE}: ${SET_ERR}"
    else
      CHANGED=$((CHANGED + 1))
      echo "  ✓ [${VENDOR}] ${TITLE}"
    fi
  done <<< "$EDGES"

  HAS_NEXT=$(echo "$RESP" | jq -r '.products.pageInfo.hasNextPage')
  if [[ "$HAS_NEXT" != "true" ]]; then break; fi
  LAST_CURSOR=$(echo "$RESP" | jq -r '.products.edges[-1].cursor')
  AFTER=$(jq -n --arg c "$LAST_CURSOR" '$c')
done

echo
if $APPLY; then
  echo "✓ Done: ${CHANGED} set to '${TEMPLATE_SUFFIX}', ${SKIPPED} already correct, ${FAILED} failed."
else
  echo "Dry run: ${CHANGED} product(s) would be set to '${TEMPLATE_SUFFIX}', ${SKIPPED} already correct."
  echo "Re-run with --apply to commit."
fi
[[ "$FAILED" -eq 0 ]]
