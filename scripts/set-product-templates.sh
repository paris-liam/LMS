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
    SEARCH_QUERY="vendor:'Supercycle' OR tag:'online-store'"
    TARGET_SUFFIX="retail"
    # vendor: and tag: filters ARE honoured by the search API (verified), so
    # the query alone identifies these products.
    SOURCE_SUFFIX_FILTER=""
    REQUIRED_TEMPLATES=("templates/product.retail.json")
    ;;
  clear-movie)
    SEARCH_QUERY="template_suffix:movie"
    TARGET_SUFFIX=""
    # LOAD-BEARING. Shopify's `template_suffix:` search filter is silently
    # IGNORED — `template_suffix:nonsense_xyz` returns every product in the
    # store (verified 2026-09-11 on the dev store: 25 of 25). So the query
    # above cannot be trusted to narrow anything, and Phase 1 re-checks each
    # product's real templateSuffix against this value instead.
    #
    # Without it this mode mutates every product whose suffix isn't already
    # empty — including the `retail` products set by the retail pass, which
    # would drop the membership plan onto the movie template and remove its
    # add-to-cart, breaking online enrollment.
    SOURCE_SUFFIX_FILTER="movie"
    # Both templates are required: product.json is the clear-movie target
    # itself, and product.retail.json must already exist from the swap —
    # its absence is the real signal that the swap hasn't happened yet, since
    # every theme ships a templates/product.json regardless.
    REQUIRED_TEMPLATES=("templates/product.json" "templates/product.retail.json")
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

# --- Preflight: the live theme must contain every template this mode needs -
THEME_Q='query Theme($f: [String!]) {
  themes(first: 1, roles: [MAIN]) {
    nodes { id name files(filenames: $f, first: 10) { nodes { filename } } }
  }
}'
THEME_VARS=$(jq -n --argjson f "$(printf '%s\n' "${REQUIRED_TEMPLATES[@]}" | jq -R . | jq -s .)" '{f: $f}')
THEME_RESP=$(shopify store execute --store "$STORE" -j -q "$THEME_Q" -v "$THEME_VARS")
THEME_NAME=$(echo "$THEME_RESP" | jq -r '.themes.nodes[0].name // empty')

if [[ -z "$THEME_NAME" ]]; then
  echo "✗ Could not read the live theme from ${STORE}" >&2
  exit 1
fi

for REQUIRED_TEMPLATE in "${REQUIRED_TEMPLATES[@]}"; do
  HAS_TEMPLATE=$(echo "$THEME_RESP" | jq -r --arg f "$REQUIRED_TEMPLATE" '.themes.nodes[0].files.nodes[] | select(.filename == $f) | .filename // empty')
  if [[ -z "$HAS_TEMPLATE" ]]; then
    echo "✗ Live theme '${THEME_NAME}' has no ${REQUIRED_TEMPLATE}." >&2
    echo "  Push the theme first, or these products will render a broken page." >&2
    exit 1
  fi
  echo "✓ Live theme '${THEME_NAME}' has ${REQUIRED_TEMPLATE}"
done
echo

# Pin sortKey: ID so ordering is stable across pages. The default relevance
# ordering on a query-filtered connection shifts as matched products stop
# matching (e.g. clear-movie removing the very suffix it's paginating on),
# which lets the shrinking result set drag matched-but-unvisited products
# out from under the cursor — pages, and whole products, get silently
# skipped. Collect-then-mutate (below) removes the interleaving that causes
# this, and the pinned sort keeps collection itself stable too.
FIND='query Find($q: String!, $after: String) {
  products(first: 100, after: $after, query: $q, sortKey: ID) {
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

# Retry budget shared by the page reads in Phase 1 and the batched mutations
# in Phase 2: 4 attempts with 3/6/9s backoff.
MAX_ATTEMPTS=4

# --- Phase 1: collect. Paginate to completion, mutating nothing. -----------
COLLECT_FILE=$(mktemp)
trap 'rm -f "$COLLECT_FILE"' EXIT

AFTER="null"
TOTAL=0
EXCLUDED=0

while :; do
  VARS=$(jq -n --arg q "$SEARCH_QUERY" --argjson after "$AFTER" '{q: $q, after: $after}')

  # Retry page reads for the same reason the mutations retry: collecting the
  # full catalogue is ~70 sequential requests, and a single transient abort
  # ("Request was aborted before it completed") would otherwise kill the run
  # under set -e before a single product is touched. Reads are side-effect
  # free, so retrying costs nothing but time.
  PAGE_ATTEMPT=1
  PAGE_OK=false
  while (( PAGE_ATTEMPT <= MAX_ATTEMPTS )); do
    if RESP=$(shopify store execute --store "$STORE" -j -q "$FIND" -v "$VARS" < /dev/null 2>/dev/null) \
       && jq -e '.products' >/dev/null 2>&1 <<< "$RESP"; then
      PAGE_OK=true
      break
    fi
    echo "  … page read failed (attempt ${PAGE_ATTEMPT}/${MAX_ATTEMPTS}), retrying" >&2
    sleep $(( PAGE_ATTEMPT * 3 ))
    PAGE_ATTEMPT=$(( PAGE_ATTEMPT + 1 ))
  done

  if ! $PAGE_OK; then
    echo "✗ Page read failed after ${MAX_ATTEMPTS} attempts — no .products payload:" >&2
    echo "$RESP" | head -c 500 >&2
    exit 1
  fi

  EDGES=$(echo "$RESP" | jq -c '.products.edges[]?')
  HAS_NEXT=$(echo "$RESP" | jq -r '.products.pageInfo.hasNextPage')

  if [[ -n "$EDGES" ]]; then
    while IFS= read -r EDGE; do
      # The search query cannot be trusted to have narrowed anything (see the
      # SOURCE_SUFFIX_FILTER note above); filter on the real value here.
      if [[ -n "$SOURCE_SUFFIX_FILTER" ]]; then
        NODE_SUFFIX=$(echo "$EDGE" | jq -r '.node.templateSuffix // ""')
        if [[ "$NODE_SUFFIX" != "$SOURCE_SUFFIX_FILTER" ]]; then
          EXCLUDED=$((EXCLUDED + 1))
          continue
        fi
      fi
      echo "$EDGE" | jq -r '[.node.id, .node.title, .node.vendor, (.node.templateSuffix // "")] | @tsv' >> "$COLLECT_FILE"
      TOTAL=$((TOTAL + 1))
    done <<< "$EDGES"
  fi

  if [[ "$HAS_NEXT" != "true" ]]; then break; fi
  LAST_CURSOR=$(echo "$RESP" | jq -r '.products.edges[-1].cursor')
  AFTER=$(jq -n --arg c "$LAST_CURSOR" '$c')
done

echo "Collected ${TOTAL} product(s) matching '${SEARCH_QUERY}'"
if [[ -n "$SOURCE_SUFFIX_FILTER" ]]; then
  echo "  (${EXCLUDED} returned by the search but excluded: templateSuffix is not '${SOURCE_SUFFIX_FILTER}')"
fi
echo

# --- Phase 2: mutate. Iterate the collected file only — no GraphQL reads. --
#
# Mutations are sent in batches of BATCH_SIZE using GraphQL aliases: one
# request carries N productUpdate calls sharing a single $suffix variable.
# One-request-per-product was measured at roughly a second each — over two
# hours for a full catalogue pass, and long enough that a transient
# ECONNRESET killed a real run after 71 products. Batching cuts ~7,000
# requests to ~280.
#
# Each batch is retried on a transport failure (the CLI exiting non-zero or
# returning something without a .data payload). Retries are safe because the
# mutation is idempotent: setting a suffix that is already set is a no-op.
BATCH_SIZE=25

CHANGED=0
SKIPPED=0
FAILED=0
PROCESSED=0

PENDING_IDS=()
PENDING_LABELS=()

flush_batch() {
  local n=${#PENDING_IDS[@]}
  (( n == 0 )) && return 0

  # mutation Batch($suffix: String, $id0: ID!, ...) { p0: productUpdate(...) ... }
  local decls="\$suffix: String" body="" i
  for (( i = 0; i < n; i++ )); do
    decls+=", \$id${i}: ID!"
    body+="  p${i}: productUpdate(product: {id: \$id${i}, templateSuffix: \$suffix}) { userErrors { field message } }"$'\n'
  done
  local query="mutation Batch(${decls}) {"$'\n'"${body}}"

  local vars
  if [[ -z "$TARGET_SUFFIX" ]]; then
    vars=$(jq -n '{suffix: null}')
  else
    vars=$(jq -n --arg s "$TARGET_SUFFIX" '{suffix: $s}')
  fi
  for (( i = 0; i < n; i++ )); do
    vars=$(jq --arg k "id${i}" --arg v "${PENDING_IDS[$i]}" '. + {($k): $v}' <<< "$vars")
  done

  local attempt=1 resp ok=false
  while (( attempt <= MAX_ATTEMPTS )); do
    # A response is only trusted when it carries a result for EVERY alias this
    # batch asked about. Merely-valid JSON is not enough: a GraphQL-level
    # error comes back as {"errors":[...]} with no per-alias keys, and
    # `.p0.userErrors[0].message // empty` yields empty for a missing key —
    # so every product in the batch would be counted CHANGED having never
    # been touched. Phase 1 already guards its reads this way; Phase 2 must
    # match it.
    if resp=$(shopify store execute --store "$STORE" --allow-mutations -j -q "$query" -v "$vars" < /dev/null 2>/dev/null) \
       && jq -e --argjson n "$n" \
            '. as $root | (($root | has("errors")) | not) and all(range($n); . as $i | $root | has("p\($i)"))' \
            >/dev/null 2>&1 <<< "$resp"; then
      ok=true
      break
    fi
    echo "  … batch request failed (attempt ${attempt}/${MAX_ATTEMPTS}), retrying" >&2
    sleep $(( attempt * 3 ))
    attempt=$(( attempt + 1 ))
  done

  if ! $ok; then
    FAILED=$(( FAILED + n ))
    echo "  ✗ batch of ${n} failed after ${MAX_ATTEMPTS} attempts" >&2
    PENDING_IDS=(); PENDING_LABELS=()
    return 0
  fi

  for (( i = 0; i < n; i++ )); do
    local err
    err=$(jq -r --arg a "p${i}" '.[$a].userErrors[0].message // empty' <<< "$resp")
    if [[ -n "$err" ]]; then
      FAILED=$(( FAILED + 1 ))
      echo "  ✗ ${PENDING_LABELS[$i]}: ${err}"
    else
      CHANGED=$(( CHANGED + 1 ))
    fi
  done

  PENDING_IDS=(); PENDING_LABELS=()
}

while IFS=$'\t' read -r -u 3 PRODUCT_ID TITLE VENDOR CURRENT; do
  PROCESSED=$((PROCESSED + 1))

  if [[ "$CURRENT" == "$TARGET_SUFFIX" ]]; then
    SKIPPED=$((SKIPPED + 1))
  elif ! $APPLY; then
    CHANGED=$((CHANGED + 1))
    echo "  would set [${VENDOR}] ${TITLE}: '${CURRENT}' -> '${TARGET_SUFFIX}'"
  else
    PENDING_IDS+=("$PRODUCT_ID")
    PENDING_LABELS+=("[${VENDOR}] ${TITLE}")
    if (( ${#PENDING_IDS[@]} >= BATCH_SIZE )); then
      flush_batch
      echo "  ... ${PROCESSED}/${TOTAL} (${CHANGED} changed, ${FAILED} failed)"
    fi
  fi
done 3< "$COLLECT_FILE"

$APPLY && flush_batch

echo
if $APPLY; then
  echo "✓ Done: ${CHANGED} changed, ${SKIPPED} already correct, ${FAILED} failed."
else
  echo "Dry run: ${CHANGED} product(s) would change, ${SKIPPED} already correct."
  echo "Re-run with --apply to commit."
fi
[[ "$FAILED" -eq 0 ]]
