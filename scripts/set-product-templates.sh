#!/usr/bin/env bash
# Two one-off migrations that invert the product-template default, so that
# imported movies need no post-import step ever again.
#
# WHY: Shopify's product-CSV import cannot set a template suffix. With the
# retail layout as the theme default, every imported movie landed on a page
# with a $0.00 "Buy now" button until someone ran set-movie-template.sh.
# Movies are 7,004 of 7,014 products, so the default is backwards. After this
# migration templates/product.json IS the movie layout and only the handful
# of non-movie products carry a suffix.
#
# MODES
#   retail       set templateSuffix=retail on non-movie products
#   clear-movie  clear the `movie` suffix wherever it is still set
#
# PREDICATE for `retail` — Vendor "Supercycle" OR tag "online-store". This is
# the same predicate as formatting-scripts/normalize.py:is_non_catalogue_product
# and it selects exactly the membership plans, the shirt and the bumper
# sticker. Do NOT use "vendor is not a format": six real movies carry Vendor
# "Little Movie Store" and would be misfiled onto the retail template.
#
# DRY RUN BY DEFAULT. Pass --apply to commit.
#
# Auth: uses the Shopify CLI's own session. Run once first if needed:
#   shopify store auth --store <store> --scopes write_products
#
# Usage:
#   ./scripts/set-product-templates.sh retail
#   ./scripts/set-product-templates.sh retail --apply
#   ./scripts/set-product-templates.sh clear-movie --apply
#   SHOPIFY_STORE=lms-sandbox-lutsfahz.myshopify.com ./scripts/set-product-templates.sh retail

set -euo pipefail
STORE="${SHOPIFY_STORE:-p0wkgv-wy.myshopify.com}"

MODE="${1:-}"
APPLY=false
if [[ "${2:-}" == "--apply" ]]; then
  APPLY=true
elif [[ -n "${2:-}" ]]; then
  echo "Unknown argument: $2 (expected --apply or nothing)" >&2
  exit 1
fi

case "$MODE" in
  retail)
    SEARCH_QUERY="vendor:Supercycle OR tag:online-store"
    TARGET_SUFFIX="retail"
    REQUIRED_TEMPLATE="templates/product.retail.json"
    ;;
  clear-movie)
    SEARCH_QUERY="template_suffix:movie"
    TARGET_SUFFIX=""
    REQUIRED_TEMPLATE="templates/product.json"
    ;;
  *)
    echo "Usage: $0 <retail|clear-movie> [--apply]" >&2
    exit 1
    ;;
esac

echo "Store: ${STORE}"
echo "Mode:  ${MODE} -> templateSuffix '${TARGET_SUFFIX}'"
$APPLY && echo "       APPLY (will modify products)" || echo "       DRY RUN (pass --apply to commit)"
echo

# --- Preflight: the live theme must contain the template we're pointing at --
THEME_Q='query Theme($f: [String!]) {
  themes(first: 1, roles: [MAIN]) {
    nodes { id name files(filenames: $f, first: 1) { nodes { filename } } }
  }
}'
THEME_VARS=$(jq -n --arg f "$REQUIRED_TEMPLATE" '{f: [$f]}')
THEME_RESP=$(shopify store execute --store "$STORE" -j -q "$THEME_Q" -v "$THEME_VARS")
THEME_NAME=$(echo "$THEME_RESP" | jq -r '.themes.nodes[0].name // empty')
HAS_TEMPLATE=$(echo "$THEME_RESP" | jq -r '.themes.nodes[0].files.nodes[0].filename // empty')

if [[ -z "$THEME_NAME" ]]; then
  echo "✗ Could not read the live theme from ${STORE}" >&2
  exit 1
fi
if [[ -z "$HAS_TEMPLATE" ]]; then
  echo "✗ Live theme '${THEME_NAME}' has no ${REQUIRED_TEMPLATE}." >&2
  echo "  Push the theme first, or these products will render a broken page." >&2
  exit 1
fi
echo "✓ Live theme '${THEME_NAME}' has ${REQUIRED_TEMPLATE}"
echo

FIND='query Find($q: String!, $after: String) {
  products(first: 100, after: $after, query: $q) {
    edges { cursor node { id title vendor templateSuffix } }
    pageInfo { hasNextPage }
  }
}'
SET_TEMPLATE='mutation SetTemplate($id: ID!, $suffix: String) {
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

    if [[ "$CURRENT" == "$TARGET_SUFFIX" ]]; then
      SKIPPED=$((SKIPPED + 1))
      continue
    fi

    if ! $APPLY; then
      CHANGED=$((CHANGED + 1))
      echo "  would set [${VENDOR}] ${TITLE}: '${CURRENT}' -> '${TARGET_SUFFIX}'"
      continue
    fi

    if [[ -z "$TARGET_SUFFIX" ]]; then
      SET_VARS=$(jq -n --arg id "$PRODUCT_ID" '{id: $id, suffix: null}')
    else
      SET_VARS=$(jq -n --arg id "$PRODUCT_ID" --arg suffix "$TARGET_SUFFIX" '{id: $id, suffix: $suffix}')
    fi
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
  echo "✓ Done: ${CHANGED} changed, ${SKIPPED} already correct, ${FAILED} failed."
else
  echo "Dry run: ${CHANGED} product(s) would change, ${SKIPPED} already correct."
  echo "Re-run with --apply to commit."
fi
[[ "$FAILED" -eq 0 ]]
