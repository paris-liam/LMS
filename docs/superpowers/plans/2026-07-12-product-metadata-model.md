# Product Metadata Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the fresh `custom.*` metafield/tag schema for movie products on the dev store, repoint the theme to it, and wire the storefront facets — so the client can upload/edit movies with dropdowns and tags.

**Architecture:** Merchant-owned Shopify metafield **definitions** in the `custom` namespace are created via the Admin GraphQL API (`metafieldDefinitionCreate`) using the repo's existing curl-based script pattern. Descriptive "film" facts and copy/commerce fields live as pinned, storefront-readable metafields; per-copy condition/availability stays owned by Supercycle. The theme's product card is repointed off the two retired keys.

> **AMENDED 2026-07-14 — flatten label to tags (genre stays a metafield):** Label/Distributor is **no longer a metafield** — it is modelled as `label-*` product tags, alongside bare curation tags `rare`/`staff-pick`/`holiday`. **Genre remains the `custom.genres` metafield** (dropdown + native facet). Net: this drops only the `custom.label` definition (Task 1 → 9 defs), removes the label `metafieldsSet` call (Task 2 adds `label-*` as a tag instead), and changes the facet story (Task 5): **Format, Decade, and Genre** are metafield facets; **Label** folds into Shopify's single combined **Product tags** filter (native Search & Discovery cannot split tags into separate named facets by prefix). Canonical label/curation vocabulary: `docs/client-guides/movie-tags.md`.

**Tech Stack:** Shopify Admin GraphQL API (version `2026-01`), bash + `curl` + `jq`, Shopify Liquid (Horizon theme), Shopify CLI (`shopify theme check` / `theme push`), Shopify Search & Discovery app.

**Design spec:** `docs/superpowers/specs/2026-07-12-product-metadata-model-design.md`

## Global Constraints

- **Namespace:** All product metafields use the `custom` namespace. **NEVER create the `supercycle` namespace** — it is app-reserved and will collide on Supercycle operations.
- **Default store:** `lms-sandbox-lutsfahz.myshopify.com` (dev). Never target production (`p0wkgv-wy.myshopify.com`) unless explicitly instructed per-operation.
- **API version:** `2026-01` (match `scripts/create-staff-pick-metaobject.sh`).
- **Definition ownership:** These are **merchant-owned** `custom.*` definitions created via Admin API. Do NOT use app TOML / `$app` namespace — that guidance is for app developers, not this theme/merchant context.
- **Condition split:** No condition metafield for serialized rental/resale stock (Supercycle owns per-item condition). `custom.media_condition` is for **non-Supercycle new-sealed retail movies only**.
- **Facets (Search & Discovery):** Format, Decade, and Genre are metafield facets. Label/Distributor is a tag axis (`label-*`) that surfaces via the single native Product-tags filter (see 2026-07-14 amendment). Availability is a separate Supercycle track, out of scope here.
- **Naming distinction:** `custom.staff_pick_note` (per-product blurb, this plan) is **separate** from the pre-existing `staff_pick` **metaobject** (homepage curated rail — `product`/`quote`/`staff_name`). Do not merge or rename them.
- **Prerequisite env (for every script):** either `SHOPIFY_ADMIN_TOKEN=shpat_…`, or `SHOPIFY_CLIENT_ID` + `SHOPIFY_CLIENT_SECRET` (exchanged for a 24h token). App must have `write_metafield_definitions`, `write_products`, `write_publications`/`write_collection_listings` scopes as needed.

---

### Task 1: Create the movie metafield definitions

Creates the `custom.*` product metafield definitions (nine, post-amendment: label is a tag; genre stays) in one idempotent script (re-runnable; "already taken" is treated as OK). Definitions are pinned and storefront-readable so they show in one panel on the product page and are readable by the theme and Search & Discovery.

**Files:**
- Create: `scripts/create-movie-metafield-definitions.sh`

**Interfaces:**
- Produces (consumed by Tasks 2, 3, 5) — product metafields in the `custom` namespace:
  - `custom.director` `single_line_text_field`
  - `custom.year` `number_integer`
  - `custom.decade` `single_line_text_field` (choices)
  - `custom.country` `single_line_text_field`
  - `custom.runtime` `number_integer`
  - `custom.genres` `list.single_line_text_field` (choices)
  - `custom.format` `single_line_text_field` (choices)
  - `custom.media_condition` `single_line_text_field` (choices)
  - *(label is a tag now, not a metafield — see 2026-07-14 amendment)*
  - `custom.staff_pick_note` `multi_line_text_field`

- [ ] **Step 1: Write the script**

Create `scripts/create-movie-metafield-definitions.sh`:

```bash
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
DEFINITIONS=$(cat <<'JSON'
[
  { "name":"Director","namespace":"custom","key":"director","ownerType":"PRODUCT","type":"single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Film director (display only)" },
  { "name":"Year","namespace":"custom","key":"year","ownerType":"PRODUCT","type":"number_integer","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Release year; drives the Decade facet" },
  { "name":"Decade","namespace":"custom","key":"decade","ownerType":"PRODUCT","type":"single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Era bucket used as a storefront facet","validations":[{"name":"choices","value":"[\"Pre-1950\",\"1950s\",\"1960s\",\"1970s\",\"1980s\",\"1990s\",\"2000s\",\"2010s\",\"2020s\"]"}] },
  { "name":"Country","namespace":"custom","key":"country","ownerType":"PRODUCT","type":"single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Country of origin (single value for v1)" },
  { "name":"Runtime (min)","namespace":"custom","key":"runtime","ownerType":"PRODUCT","type":"number_integer","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Runtime in minutes; display as e.g. 142 min" },
  { "name":"Genres","namespace":"custom","key":"genres","ownerType":"PRODUCT","type":"list.single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"One or more genres; storefront facet","validations":[{"name":"choices","value":"[\"Action\",\"Adventure\",\"Animation\",\"Comedy\",\"Crime\",\"Cult\",\"Documentary\",\"Drama\",\"Fantasy\",\"Horror\",\"Musical\",\"Mystery\",\"Noir\",\"Romance\",\"Sci-Fi\",\"Thriller\",\"War\",\"Western\"]"}] },
  { "name":"Format","namespace":"custom","key":"format","ownerType":"PRODUCT","type":"single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Disc format; storefront facet","validations":[{"name":"choices","value":"[\"Blu-ray\",\"DVD\",\"4K UHD\",\"VHS\"]"}] },
  { "name":"Label / Distributor","namespace":"custom","key":"label","ownerType":"PRODUCT","type":"single_line_text_field","pin":true,"access":{"storefront":"PUBLIC_READ"},"description":"Boutique label / distributor; storefront facet","validations":[{"name":"choices","value":"[\"Criterion\",\"A24\",\"Arrow\",\"Kino Lorber\",\"Second Sight\",\"Vinegar Syndrome\",\"Other\"]"}] },
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
```

- [ ] **Step 2: Make it executable and run it**

Run:
```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
chmod +x scripts/create-movie-metafield-definitions.sh
./scripts/create-movie-metafield-definitions.sh
```
Expected: ten lines, each `✓ custom.<key> created` (or `= … already exists (ok)` on a re-run), then the final ✓ summary. No `✗`.

- [ ] **Step 3: Verify the definitions exist via a read-back query**

Run (reuses `SHOPIFY_ADMIN_TOKEN` from the same shell, or re-export it):
```bash
curl -sS "https://lms-sandbox-lutsfahz.myshopify.com/admin/api/2026-01/graphql.json" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
  -d '{"query":"{ metafieldDefinitions(first:50, ownerType: PRODUCT, namespace:\"custom\") { nodes { key type { name } } } }"}' \
  | jq -r '.data.metafieldDefinitions.nodes[] | "\(.key)\t\(.type.name)"' | sort
```
Expected output includes exactly these rows (label is a tag now, so absent; genre present):
```
country	single_line_text_field
decade	single_line_text_field
director	single_line_text_field
format	single_line_text_field
genres	list.single_line_text_field
media_condition	single_line_text_field
runtime	number_integer
staff_pick_note	multi_line_text_field
year	number_integer
```

- [ ] **Step 4: Commit**

```bash
git add scripts/create-movie-metafield-definitions.sh
git commit -m "Add script creating movie product metafield definitions (custom.*)"
```

---

### Task 2: Seed a reference movie and verify value round-trip

Proves the choice validations accept real values and gives Tasks 3 & 5 a concrete product to render/filter. Sets every field on one existing product via `metafieldsSet`, adds the `rare` + `staff-pick` tags, then reads it back.

**Files:**
- Create: `scripts/seed-reference-movie.sh`

**Interfaces:**
- Consumes (from Task 1): the ten `custom.*` definitions.
- Produces (consumed by Tasks 3, 5): one product with populated `custom.*` values and tags `rare`, `staff-pick`.

- [ ] **Step 1: Pick a product ID to seed**

Run (lists a few products so you can copy one numeric ID):
```bash
curl -sS "https://lms-sandbox-lutsfahz.myshopify.com/admin/api/2026-01/graphql.json" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
  -d '{"query":"{ products(first:5) { nodes { id title } } }"}' | jq -r '.data.products.nodes[] | "\(.id)\t\(.title)"'
```
Expected: up to five `gid://shopify/Product/…<TAB>Title` rows. Copy one GID for the next step.

- [ ] **Step 2: Write the seed script**

Create `scripts/seed-reference-movie.sh`:

```bash
#!/usr/bin/env bash
# Seeds one product with sample custom.* movie values + curation tags (dev store by default).
# Usage:
#   export SHOPIFY_ADMIN_TOKEN=shpat_...   # or CLIENT_ID/SECRET as in the definitions script
#   export PRODUCT_GID="gid://shopify/Product/1234567890"
#   ./scripts/seed-reference-movie.sh

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"
API_VERSION="2026-01"
: "${PRODUCT_GID:?Set PRODUCT_GID to a gid://shopify/Product/... value}"

if [[ -z "${SHOPIFY_ADMIN_TOKEN:-}" ]]; then
  if [[ -z "${SHOPIFY_CLIENT_ID:-}" || -z "${SHOPIFY_CLIENT_SECRET:-}" ]]; then
    echo "Set SHOPIFY_ADMIN_TOKEN, or SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET." >&2; exit 1
  fi
  TOKEN_RESPONSE=$(curl -sS "https://${STORE}/admin/oauth/access_token" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg id "$SHOPIFY_CLIENT_ID" --arg secret "$SHOPIFY_CLIENT_SECRET" \
      '{grant_type:"client_credentials", client_id:$id, client_secret:$secret}')")
  SHOPIFY_ADMIN_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token // empty')
  [[ -n "$SHOPIFY_ADMIN_TOKEN" ]] || { echo "Token exchange failed"; echo "$TOKEN_RESPONSE" | jq .; exit 1; }
fi

# metafieldsSet — note list value is a JSON-array string; integers are strings.
SET_QUERY='mutation Set($m:[MetafieldsSetInput!]!){ metafieldsSet(metafields:$m){ metafields{ key } userErrors{ field message } } }'
METAFIELDS=$(jq -n --arg id "$PRODUCT_GID" '[
  {ownerId:$id, namespace:"custom", key:"director",        type:"single_line_text_field",      value:"Ridley Scott"},
  {ownerId:$id, namespace:"custom", key:"year",            type:"number_integer",              value:"1982"},
  {ownerId:$id, namespace:"custom", key:"decade",          type:"single_line_text_field",      value:"1980s"},
  {ownerId:$id, namespace:"custom", key:"country",         type:"single_line_text_field",      value:"United States"},
  {ownerId:$id, namespace:"custom", key:"runtime",         type:"number_integer",              value:"117"},
  {ownerId:$id, namespace:"custom", key:"genres",          type:"list.single_line_text_field", value:"[\"Sci-Fi\",\"Noir\"]"},
  {ownerId:$id, namespace:"custom", key:"format",          type:"single_line_text_field",      value:"Blu-ray"},
  {ownerId:$id, namespace:"custom", key:"label",           type:"single_line_text_field",      value:"Criterion"},
  {ownerId:$id, namespace:"custom", key:"media_condition", type:"single_line_text_field",      value:"Sealed / New"},
  {ownerId:$id, namespace:"custom", key:"staff_pick_note", type:"multi_line_text_field",       value:"A neon-drenched touchstone — our pick for the shelf."}
]')
RESP=$(curl -sS "https://${STORE}/admin/api/${API_VERSION}/graphql.json" \
  -H "Content-Type: application/json" -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
  -d "$(jq -n --arg q "$SET_QUERY" --argjson m "$METAFIELDS" '{query:$q, variables:{m:$m}}')")
echo "$RESP" | jq '.data.metafieldsSet.userErrors'
[[ "$(echo "$RESP" | jq -r '.data.metafieldsSet.userErrors | length')" == "0" ]] || { echo "metafieldsSet failed"; exit 1; }

# Curation tags
TAG_QUERY='mutation Tag($id:ID!,$tags:[String!]!){ tagsAdd(id:$id, tags:$tags){ userErrors{ message } } }'
curl -sS "https://${STORE}/admin/api/${API_VERSION}/graphql.json" \
  -H "Content-Type: application/json" -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
  -d "$(jq -n --arg q "$TAG_QUERY" --arg id "$PRODUCT_GID" '{query:$q, variables:{id:$id, tags:["rare","staff-pick"]}}')" \
  | jq '.data.tagsAdd.userErrors'

echo "✓ Seeded ${PRODUCT_GID}"
```

- [ ] **Step 3: Run it**

Run:
```bash
chmod +x scripts/seed-reference-movie.sh
PRODUCT_GID="gid://shopify/Product/<paste-id>" ./scripts/seed-reference-movie.sh
```
Expected: two `[]` (empty userErrors arrays) then `✓ Seeded …`.

- [ ] **Step 4: Verify the values read back**

Run (substitute the same GID):
```bash
curl -sS "https://lms-sandbox-lutsfahz.myshopify.com/admin/api/2026-01/graphql.json" \
  -H "Content-Type: application/json" -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
  -d '{"query":"{ product(id:\"gid://shopify/Product/<paste-id>\"){ tags metafields(first:20, namespace:\"custom\"){ nodes{ key jsonValue } } } }"}' \
  | jq '{tags:.data.product.tags, fields:[.data.product.metafields.nodes[] | {(.key): .jsonValue}]}'
```
Expected: `tags` contains `"rare"` and `"staff-pick"`; `fields` shows all ten keys, with `genres` as the JSON array `["Sci-Fi","Noir"]`.

- [ ] **Step 5: Commit**

```bash
git add scripts/seed-reference-movie.sh
git commit -m "Add reference-movie seed script for metafield/tag verification"
```

---

### Task 3: Repoint the product card off the retired keys

The card currently reads `custom.condition` (retired → `custom.media_condition`) and the `custom.rare` boolean (retired → the `rare` tag). Update both reads and the data-contract comment. No visual/CSS change.

**Files:**
- Modify: `theme/lms-redesign-v4/snippets/lms-product-card.liquid`

**Interfaces:**
- Consumes (from Tasks 1–2): `custom.media_condition` value and the `rare` tag on the seeded product.

- [ ] **Step 1: Update the data-contract comment**

In `theme/lms-redesign-v4/snippets/lms-product-card.liquid`, replace these two comment lines (currently lines 13–14):
```liquid
  - Condition:  card_product.metafields.custom.condition (e.g. New / Used)
  - Rare flag:  card_product.metafields.custom.rare      (boolean)
```
with:
```liquid
  - Condition:  card_product.metafields.custom.media_condition (retail new-sealed only; used/rental copies use Supercycle item condition)
  - Rare flag:  card_product.tags contains 'rare'
```

- [ ] **Step 2: Repoint the Rare badge to the tag**

Replace (currently lines 30–32):
```liquid
      {%- if card_product.metafields.custom.rare.value -%}
        <span class="lms-badge lms-badge--brick lms-product-card__rare">Rare</span>
      {%- endif -%}
```
with:
```liquid
      {%- if card_product.tags contains 'rare' -%}
        <span class="lms-badge lms-badge--brick lms-product-card__rare">Rare</span>
      {%- endif -%}
```

- [ ] **Step 3: Repoint the Condition badge to media_condition**

Replace (currently lines 47–49):
```liquid
        {%- if card_product.metafields.custom.condition != blank -%}
          <span class="lms-badge lms-badge--muted">{{ card_product.metafields.custom.condition.value }}</span>
        {%- endif -%}
```
with:
```liquid
        {%- if card_product.metafields.custom.media_condition != blank -%}
          <span class="lms-badge lms-badge--muted">{{ card_product.metafields.custom.media_condition.value }}</span>
        {%- endif -%}
```

- [ ] **Step 4: Confirm no stale references remain**

Run:
```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
grep -n "custom.condition\|custom.rare" theme/lms-redesign-v4/snippets/lms-product-card.liquid || echo "CLEAN"
```
Expected: `CLEAN`.

- [ ] **Step 5: Lint the theme**

Run:
```bash
shopify theme check --path theme/lms-redesign-v4
```
Expected: no errors introduced for `snippets/lms-product-card.liquid` (pre-existing warnings elsewhere are fine).

- [ ] **Step 6: Commit**

```bash
git add theme/lms-redesign-v4/snippets/lms-product-card.liquid
git commit -m "Repoint product card: rare→tag, condition→media_condition"
```

- [ ] **Step 7 (recommended): Visual check on the dev store**

Push the snippet to the working dev theme and view a collection page:
```bash
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 140918915134 --only snippets/lms-product-card.liquid
```
Then open a collection containing the seeded product (use the dev store storefront password from memory `dev-store-storefront-password`) and confirm the seeded product shows a **Rare** badge and a **Sealed / New** badge. If you cannot push mid-plan, rely on Steps 4–5 as the gate.

---

### Task 4: Create curation automated collections

Creates automatic (rule-based) collections driven by the curation tags, so tagging a product files it automatically. Distinct from the pre-existing `staff_pick` metaobject (homepage rail).

**Files:**
- Create: `scripts/create-curation-collections.sh`

**Interfaces:**
- Consumes (from Task 2): products carrying `rare` / `staff-pick` tags.
- Produces: automatic collections `Staff Picks`, `Rare Finds`, `Holiday Movies`.

- [ ] **Step 1: Write the script**

Create `scripts/create-curation-collections.sh`:

```bash
#!/usr/bin/env bash
# Creates tag-driven automatic collections (dev store by default). Idempotent-ish:
# a duplicate-handle userError is treated as OK.
# Usage: same auth env as the other scripts. ./scripts/create-curation-collections.sh

set -euo pipefail
STORE="${SHOPIFY_STORE:-lms-sandbox-lutsfahz.myshopify.com}"
API_VERSION="2026-01"

if [[ -z "${SHOPIFY_ADMIN_TOKEN:-}" ]]; then
  if [[ -z "${SHOPIFY_CLIENT_ID:-}" || -z "${SHOPIFY_CLIENT_SECRET:-}" ]]; then
    echo "Set SHOPIFY_ADMIN_TOKEN, or SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET." >&2; exit 1
  fi
  TOKEN_RESPONSE=$(curl -sS "https://${STORE}/admin/oauth/access_token" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg id "$SHOPIFY_CLIENT_ID" --arg secret "$SHOPIFY_CLIENT_SECRET" \
      '{grant_type:"client_credentials", client_id:$id, client_secret:$secret}')")
  SHOPIFY_ADMIN_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token // empty')
  [[ -n "$SHOPIFY_ADMIN_TOKEN" ]] || { echo "Token exchange failed"; echo "$TOKEN_RESPONSE" | jq .; exit 1; }
fi

QUERY='mutation Create($input: CollectionInput!) {
  collectionCreate(input: $input) { collection { id handle } userErrors { field message } }
}'

# title | tag
COLLECTIONS=$(cat <<'JSON'
[
  { "title":"Staff Picks",   "tag":"staff-pick" },
  { "title":"Rare Finds",    "tag":"rare" },
  { "title":"Holiday Movies","tag":"holiday" }
]
JSON
)

echo "$COLLECTIONS" | jq -c '.[]' | while read -r C; do
  TITLE=$(echo "$C" | jq -r '.title'); TAG=$(echo "$C" | jq -r '.tag')
  INPUT=$(jq -n --arg t "$TITLE" --arg tag "$TAG" '{
    title:$t,
    ruleSet:{ appliedDisjunctively:false, rules:[{ column:"TAG", relation:"EQUALS", condition:$tag }] }
  }')
  RESP=$(curl -sS "https://${STORE}/admin/api/${API_VERSION}/graphql.json" \
    -H "Content-Type: application/json" -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
    -d "$(jq -n --arg q "$QUERY" --argjson i "$INPUT" '{query:$q, variables:{input:$i}}')")
  ERR=$(echo "$RESP" | jq -r '.data.collectionCreate.userErrors[0].message // empty')
  if [[ -n "$ERR" ]]; then
    if echo "$ERR" | grep -qiE 'taken|already|in use'; then echo "  = ${TITLE}: exists (ok)";
    else echo "  ✗ ${TITLE}: ${ERR}"; exit 1; fi
  else
    echo "  ✓ ${TITLE} (tag='${TAG}') → $(echo "$RESP" | jq -r '.data.collectionCreate.collection.handle')"
  fi
done
echo "✓ Curation collections ready."
```

- [ ] **Step 2: Run it**

Run:
```bash
chmod +x scripts/create-curation-collections.sh
./scripts/create-curation-collections.sh
```
Expected: `✓ Staff Picks …`, `✓ Rare Finds …`, `✓ Holiday Movies …` (or `= … exists (ok)` on re-run). No `✗`.

- [ ] **Step 3: Verify the seeded product landed in its collections**

Run:
```bash
curl -sS "https://lms-sandbox-lutsfahz.myshopify.com/admin/api/2026-01/graphql.json" \
  -H "Content-Type: application/json" -H "X-Shopify-Access-Token: ${SHOPIFY_ADMIN_TOKEN}" \
  -d '{"query":"{ collections(first:10, query:\"title:Rare Finds OR title:Staff Picks\"){ nodes{ title productsCount { count } } } }"}' \
  | jq -r '.data.collections.nodes[] | "\(.title): \(.productsCount.count) product(s)"'
```
Expected: `Rare Finds` and `Staff Picks` each report ≥ 1 product (the seeded one). (Automatic collection membership can take a few seconds to populate.)

- [ ] **Step 4: Commit**

```bash
git add scripts/create-curation-collections.sh
git commit -m "Add script creating tag-driven curation collections"
```

---

### Task 5: Configure the storefront facets (Search & Discovery)

Adds the four approved metafield filters. This is Shopify admin app configuration — no repo change; the gate is a rendered facet on a collection page.

**Files:** none (Shopify Search & Discovery app configuration).

**Interfaces:**
- Consumes (from Task 1): storefront-readable `custom.format`, `custom.genres`, `custom.decade`, `custom.label` definitions.

- [ ] **Step 1: Add the four filters**

In Shopify admin → **Apps → Search & Discovery → Filters → Add filter**:
- `custom.format` → label "Format" (Source = Metafield)
- `custom.decade` → label "Decade" (Source = Metafield)
- `custom.genres` → label "Genre" (Source = Metafield)
- **Product tags** filter → enable it. Label (`label-*`) and curation tags surface here in **one combined facet** — native Search & Discovery cannot give Label its own named filter. If a distinct named "Label" facet is required, either move label to a metafield or add custom prefix-grouping in the theme's `filters.liquid` (out of scope for this amendment).

Leave the default variant/availability filters as-is for now (Supercycle availability is a separate track). Save.

- [ ] **Step 2: Ensure the collection template renders filters**

Confirm the collection section's Filters block (`theme/lms-redesign-v4/blocks/filters.liquid`) has **Enable filtering** turned on for the collection where you'll verify (theme editor → Collection → Filters block → "Enable filtering"). The block already renders whatever filters Search & Discovery exposes.

- [ ] **Step 3: Verify facets render on the storefront**

Open a collection page on the dev store (authenticate with the storefront password from memory `dev-store-storefront-password`). In the filter drawer/bar, confirm **Format, Genre, Decade, Label / Distributor** appear, and that selecting **Format → Blu-ray** narrows results to include the seeded product.
Expected: all four facets visible; filtering by `Blu-ray` returns the seeded reference movie.

- [ ] **Step 4: Record completion**

No commit (store-side config). Note in the PR/summary that Search & Discovery filters were configured for Format, Genre, Decade, Label.

---

### Task 6: Write the client upload cheat-sheet

A short, client-facing reference so the shop owner can add/edit movies confidently — the "ease of use" goal made concrete.

**Files:**
- Create: `docs/client-guides/adding-a-movie.md`

**Interfaces:**
- Consumes: the final field/tag names from Tasks 1–4.

- [ ] **Step 1: Write the guide**

Create `docs/client-guides/adding-a-movie.md`:

```markdown
# Adding or editing a movie

Each product = one physical listing (one format/copy). Fill these in on the product page.

## Description
Put the **synopsis** in the normal product **Description** box. Add the cover art as the product image.

## Movie fields (Metafields panel, pinned)
| Field | How to fill it |
|---|---|
| Director | Type the director's name. |
| Year | Release year (number). |
| Decade | Pick the era from the dropdown (must match the year). |
| Country | Country of origin. |
| Runtime (min) | Runtime in minutes (number). |
| Genres | Tick every genre that applies. |
| Format | Pick one: Blu-ray / DVD / 4K UHD / VHS. |
| Label / Distributor | Pick the label (Criterion, A24, …). Choose "Other" if not listed. |
| Media condition | **Only for brand-new sealed stock you sell outright.** Leave blank for rental/resale copies — their condition is tracked per copy in Supercycle. |
| Staff pick note | The shelf blurb. Also add the `staff-pick` tag (below) so it shows in Staff Picks. |

## Curation tags (Tags box)
- `staff-pick` → files it under **Staff Picks** (pair with a Staff pick note).
- `rare` → files it under **Rare Finds** and shows a "Rare" badge.
- `holiday` → files it under **Holiday Movies**.

## Adding a new genre or label
If a genre or label isn't in the dropdown, an admin adds it once in
**Settings → Custom data → Products → [the field] → Edit choices**. After that it
appears for every product and as a storefront filter.

## What NOT to touch
Anything under a **Supercycle** heading (rental/resale/membership, per-copy
condition, serials, availability) is managed by Supercycle — don't edit it here.
```

- [ ] **Step 2: Verify it renders**

Run:
```bash
cd /Users/liamparis/web-projects/personal/LMS-sandbox
test -f docs/client-guides/adding-a-movie.md && head -5 docs/client-guides/adding-a-movie.md
```
Expected: the first lines of the guide print.

- [ ] **Step 3: Commit**

```bash
git add docs/client-guides/adding-a-movie.md
git commit -m "Add client cheat-sheet for adding movies"
```

---

## Notes / deferred (from the spec's open items)

- **Decade auto-fill:** currently a manual dropdown. Optionally add a Shopify Flow later (`Product created/updated` → set `custom.decade` from `custom.year`) to drop a client step. Not required for this plan.
- **Country co-productions:** modelled as a single value; revisit `list.single_line_text_field` if multi-country display is wanted.
- **Genre/label growth:** adding values = editing the definition's choices (documented in the client guide). If a vocabulary churns heavily, revisit a metaobject for that field.
- **Film metaobject migration:** Layer 1 fields (`director`, `year`, `decade`, `country`, `runtime`, `genres`) are named to lift into a `custom.film` metaobject later; out of scope now.
- **Supercycle item-condition read (DEFERRED):** the spec's display rule is "if a Supercycle item condition exists, show that; else fall back to `custom.media_condition`." Task 3 implements only the `custom.media_condition` side. Reading a serialized copy's condition in Liquid belongs to the Supercycle rendering track (Layer 4 / resale), not this metadata-model plan — wiring it here would cross the condition-split boundary the spec sets. Deferred to that track; until then the card badge simply doesn't render for rental/resale copies (graceful, never a wrong value).

## Self-review

- **Spec coverage:** Layer 0 native fields (guide, Step 1 of Task 6) ✓; Layer 1 + Layer 2 metafields (Task 1) ✓; condition split (Task 1 `media_condition` description + Task 3 comment) ✓ — the retail side only; the Supercycle item-condition fallback is explicitly deferred (see Notes); Layer 3 tag curation + collections (Task 4) ✓; Layer 4 Supercycle boundary (guide "What NOT to touch" + constraints) ✓; facets (Task 5) ✓; client ease-of-use (Task 6) ✓; theme impact (Task 3) ✓; migration naming (Notes) ✓.
- **Placeholder scan:** every code/command step is complete; `<paste-id>` is an intentional user-supplied product GID with a preceding discovery step, not a plan gap.
- **Type/name consistency:** the ten `custom.*` keys and the tags `rare`/`staff-pick`/`holiday` are identical across Tasks 1, 2, 3, 4, 5, and 6.
