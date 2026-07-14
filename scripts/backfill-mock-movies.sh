#!/usr/bin/env bash
# Back-fills EVERY product with varied MOCK movie data to demo the inventory grid
# and the storefront search/facet pages (dev store by default).
#
# The values are deliberately spread across all facet choices (every genre, decade,
# format, and label appears; rare/staff-pick/holiday are sprinkled) so filters have
# real coverage. They are NOT accurate film data — this is demo seed only.
#
# Model (matches the metadata plan): metafields custom.{director,year,decade,country,
# runtime,genres,format,media_condition,staff_pick_note}; label + curation are tags
# (label-*, rare, staff-pick, holiday).
#
# Usage:
#   export SHOPIFY_ADMIN_TOKEN=shpat_...          # or CLIENT_ID/SECRET as in the other scripts
#   ./scripts/backfill-mock-movies.sh             # apply to all products
#   DRY_RUN=1 ./scripts/backfill-mock-movies.sh   # print the first 12 generated payloads, write nothing (no token needed)
#   LIMIT=20 ./scripts/backfill-mock-movies.sh    # only touch the first 20 products

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"
API_VERSION="2026-01"
DRY_RUN="${DRY_RUN:-0}"
LIMIT="${LIMIT:-0}"   # 0 = no limit

# ---- Mock value pools (indexed by product position for an even spread) ----
GENRES=(Action Adventure Animation Comedy Crime Cult Documentary Drama Fantasy Horror Musical Mystery Noir Romance "Sci-Fi" Thriller War Western)
DECADES=(Pre-1950 1950s 1960s 1970s 1980s 1990s 2000s 2010s 2020s)
DECADE_YEARS=(1948 1955 1963 1974 1985 1996 2004 2015 2022)
FORMATS=("Blu-ray" DVD "4K UHD" VHS)
LABEL_SLUGS=(criterion a24 arrow kino-lorber second-sight vinegar-syndrome other)
CONDITIONS=("Sealed / New" "Like New" Good Fair)
DIRECTORS=("Agnès Varda" "Akira Kurosawa" "Wong Kar-wai" "David Lynch" "Céline Sciamma" "Spike Lee" "Greta Gerwig" "Bong Joon-ho" "Chantal Akerman" "Paul Thomas Anderson" "Lynne Ramsay" "Guillermo del Toro")
COUNTRIES=("United States" "France" "Japan" "South Korea" "United Kingdom" "Italy" "Mexico" "Germany" "Sweden" "Hong Kong")
NOTES=("A neon-drenched touchstone — top of our shelf." "The one we press into everyone's hands." "Quietly devastating; stays with you for days." "Pure craft — a director at the height of their powers." "Weird, warm, and completely unforgettable." "Comfort viewing with real teeth.")

# ---- Auth (token, or client-credentials exchange) ----
if [[ "$DRY_RUN" != "1" ]]; then
  if [[ -z "${SHOPIFY_ADMIN_TOKEN:-}" ]]; then
    if [[ -z "${SHOPIFY_CLIENT_ID:-}" || -z "${SHOPIFY_CLIENT_SECRET:-}" ]]; then
      echo "Set SHOPIFY_ADMIN_TOKEN, or SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET (or run with DRY_RUN=1)." >&2; exit 1
    fi
    TOKEN_RESPONSE=$(curl -sS "https://${STORE}/admin/oauth/access_token" \
      -H "Content-Type: application/json" \
      -d "$(jq -n --arg id "$SHOPIFY_CLIENT_ID" --arg secret "$SHOPIFY_CLIENT_SECRET" \
        '{grant_type:"client_credentials", client_id:$id, client_secret:$secret}')")
    SHOPIFY_ADMIN_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token // empty')
    [[ -n "$SHOPIFY_ADMIN_TOKEN" ]] || { echo "Token exchange failed"; echo "$TOKEN_RESPONSE" | jq .; exit 1; }
  fi
fi

api() {  # api <json-body>
  curl -sS "https://${STORE}/admin/api/${API_VERSION}/graphql.json" \
    -H "Content-Type: application/json" \
    -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
    -d "$1"
}

# ---- Collect product GIDs (paginated) ----
GIDS=()
if [[ "$DRY_RUN" == "1" ]]; then
  for n in $(seq 1 12); do GIDS+=("gid://shopify/Product/$((1000 + n))"); done
else
  CURSOR=null
  Q='query($c:String){ products(first:250, after:$c){ pageInfo{ hasNextPage endCursor } nodes{ id } } }'
  while :; do
    RESP=$(api "$(jq -n --arg q "$Q" --argjson c "$CURSOR" '{query:$q, variables:{c:$c}}')")
    if echo "$RESP" | jq -e '.errors' >/dev/null 2>&1; then
      echo "GraphQL error listing products:"; echo "$RESP" | jq -c '.errors'; exit 1
    fi
    while IFS= read -r gid; do [[ -n "$gid" ]] && GIDS+=("$gid"); done \
      < <(echo "$RESP" | jq -r '.data.products.nodes[].id')
    [[ "$(echo "$RESP" | jq -r '.data.products.pageInfo.hasNextPage')" == "true" ]] || break
    CURSOR=$(echo "$RESP" | jq -c '.data.products.pageInfo.endCursor')
  done
fi

TOTAL=${#GIDS[@]}
echo "Products found: ${TOTAL}${DRY_RUN:+ (DRY_RUN synthetic)}"
[[ "$TOTAL" -gt 0 ]] || { echo "No products to back-fill."; exit 0; }

SET_QUERY='mutation Set($m:[MetafieldsSetInput!]!){ metafieldsSet(metafields:$m){ metafields{ key } userErrors{ field message } } }'
TAG_QUERY='mutation Tag($id:ID!,$tags:[String!]!){ tagsAdd(id:$id, tags:$tags){ userErrors{ message } } }'

i=0
for GID in "${GIDS[@]}"; do
  [[ "$LIMIT" -gt 0 && "$i" -ge "$LIMIT" ]] && break

  # Deterministic spread by position
  di=$(( i % ${#DECADES[@]} ))
  DECADE="${DECADES[$di]}"; YEAR="${DECADE_YEARS[$di]}"
  FORMAT="${FORMATS[$(( i % ${#FORMATS[@]} ))]}"
  DIRECTOR="${DIRECTORS[$(( i % ${#DIRECTORS[@]} ))]}"
  COUNTRY="${COUNTRIES[$(( i % ${#COUNTRIES[@]} ))]}"
  LABEL_SLUG="${LABEL_SLUGS[$(( i % ${#LABEL_SLUGS[@]} ))]}"
  RUNTIME=$(( 78 + (i * 13) % 97 ))

  # 1–3 genres per product
  G1="${GENRES[$(( i % ${#GENRES[@]} ))]}"; G2=""; G3=""
  (( i % 2 == 0 )) && G2="${GENRES[$(( (i + 6) % ${#GENRES[@]} ))]}"
  (( i % 3 == 0 )) && G3="${GENRES[$(( (i + 11) % ${#GENRES[@]} ))]}"
  GENRES_JSON=$(jq -cn --arg a "$G1" --arg b "$G2" --arg c "$G3" '[ $a, $b, $c ] | map(select(. != ""))')

  # Curation + condition subsets
  RARE=false;  (( i % 5 == 0 )) && RARE=true
  SP=false;    (( i % 4 == 0 )) && SP=true
  HOL=false;   (( i % 9 == 0 )) && HOL=true
  COND=""; (( i % 3 == 0 )) && COND="${CONDITIONS[$(( (i / 3) % ${#CONDITIONS[@]} ))]}"
  NOTE=""; [[ "$SP" == "true" ]] && NOTE="${NOTES[$(( i % ${#NOTES[@]} ))]}"

  METAFIELDS=$(jq -n --arg id "$GID" \
    --arg director "$DIRECTOR" --arg year "$YEAR" --arg decade "$DECADE" \
    --arg country "$COUNTRY" --arg runtime "$RUNTIME" --argjson genres "$GENRES_JSON" \
    --arg format "$FORMAT" --arg cond "$COND" --arg note "$NOTE" '
    [ {ownerId:$id, namespace:"custom", key:"director", type:"single_line_text_field",      value:$director},
      {ownerId:$id, namespace:"custom", key:"year",     type:"number_integer",              value:$year},
      {ownerId:$id, namespace:"custom", key:"decade",   type:"single_line_text_field",      value:$decade},
      {ownerId:$id, namespace:"custom", key:"country",  type:"single_line_text_field",      value:$country},
      {ownerId:$id, namespace:"custom", key:"runtime",  type:"number_integer",              value:$runtime},
      {ownerId:$id, namespace:"custom", key:"genres",   type:"list.single_line_text_field", value:($genres|tostring)},
      {ownerId:$id, namespace:"custom", key:"format",   type:"single_line_text_field",      value:$format}
    ]
    + (if $cond == "" then [] else [{ownerId:$id, namespace:"custom", key:"media_condition", type:"single_line_text_field", value:$cond}] end)
    + (if $note == "" then [] else [{ownerId:$id, namespace:"custom", key:"staff_pick_note", type:"multi_line_text_field", value:$note}] end)
  ')

  TAGS_JSON=$(jq -cn --arg label "label-$LABEL_SLUG" \
    --argjson rare "$RARE" --argjson sp "$SP" --argjson hol "$HOL" '
    [$label]
    + (if $rare then ["rare"] else [] end)
    + (if $sp   then ["staff-pick"] else [] end)
    + (if $hol  then ["holiday"] else [] end)')

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "── ${GID}"
    echo "   tags: $TAGS_JSON"
    echo "   fields: $(echo "$METAFIELDS" | jq -c 'map({(.key): .value})')"
  else
    RESP=$(api "$(jq -n --arg q "$SET_QUERY" --argjson m "$METAFIELDS" '{query:$q, variables:{m:$m}}')")
    ERR=$(echo "$RESP" | jq -r '.data.metafieldsSet.userErrors[0].message // empty')
    [[ -z "$ERR" ]] || { echo "  ✗ ${GID} metafields: ${ERR}"; exit 1; }
    RESP=$(api "$(jq -n --arg q "$TAG_QUERY" --arg id "$GID" --argjson t "$TAGS_JSON" '{query:$q, variables:{id:$id, tags:$t}}')")
    ERR=$(echo "$RESP" | jq -r '.data.tagsAdd.userErrors[0].message // empty')
    [[ -z "$ERR" ]] || { echo "  ✗ ${GID} tags: ${ERR}"; exit 1; }
    echo "  ✓ ${GID}"
  fi
  i=$(( i + 1 ))
done

echo
echo "✓ Back-filled ${i} product(s) with mock movie data.${DRY_RUN:+ (DRY_RUN — nothing written)}"