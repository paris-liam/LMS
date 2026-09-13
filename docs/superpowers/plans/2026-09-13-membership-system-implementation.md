# Membership System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Shopify-native membership system (product, checkout capture, Flow automations, discount, terms page) end-to-end on the **dev store only**, in the current branch.

**Architecture:** One subscription-only Shopify product sold via the native Shopify Subscriptions app ($160/yr, auto-renew), a dedicated product template that captures terms-acceptance + birthday as line-item properties, two Shopify Flow automations that tag the customer, sync a Libib patron, and mirror birthday/barcode onto customer metafields, and a segment-scoped automatic discount for the 10% member perk.

**Tech Stack:** Shopify theme (Horizon/OS 2.0, Liquid + JSON templates), Shopify Admin GraphQL via `shopify store execute`, Shopify Subscriptions app, Shopify Flow, Libib REST API.

**Spec:** `docs/superpowers/specs/2026-09-13-membership-system-design.md`

## Global Constraints

- **Store:** every step in this plan targets `lms-sandbox-lutsfahz.myshopify.com` (dev store) only. Do not touch `p0wkgv-wy.myshopify.com` (production) as part of this plan.
- **Branch:** all work happens on the current branch (`launch-prep-membership-faq-terms`). No new branch.
- **Live theme:** the dev store's actual published (`MAIN`) theme is `142364311614` ("lms-9.11") — **not** `140918915134` as CLAUDE.md currently states (verified via Admin API 2026-09-13; that theme is `UNPUBLISHED`). Every theme push/pull in this plan targets `142364311614`. Task 11 corrects the stale doc.
- **Selling plan:** yearly interval, count 1, $160.00, auto-renew — exact values from the spec, not open to interpretation.
- **Discount:** 10% off, automatic, scoped to customers tagged `Active Member`. Per spec §6/research done during brainstorming: Shopify automatic discounts do not apply to subscription recurring billing (confirmed Shopify platform limitation) and do not apply to gift cards (Shopify default) — so no special exclusion logic is needed; `items: { all: true }` is correct as-is.
- **Tag name:** `Active Member` (no existing theme code depends on any other tag string — verified by grep before this plan was written).
- **Libib API:** base URL `https://api.libib.com`, auth via `x-api-key` and `x-api-user` headers. **Prerequisite before Task 8:** obtain both values from the client's Libib account settings. Test runs against this API create real patron records — there is no Libib sandbox — so Task 8 and Task 10 both end with deleting any test patrons created.
- **Metafield namespace:** `custom`, matching the rest of the repo's product metafields.

---

## Task 1: Archive the stale dev-store membership product

The dev store already has a product ("LMS Annual Membership", handle `basic`, $0.00, tag `Supercycle product`) with a selling plan group attached, left over from an earlier abandoned attempt. Decision (confirmed with the client 2026-09-13): archive it and build a clean product from scratch, rather than risk inheriting unknown misconfiguration.

**Files:** none (Admin API only).

- [ ] **Step 1: Confirm the product is the one to archive**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com \
  --query 'query { product(id: "gid://shopify/Product/8156540895294") { id title handle status tags } }'
```

Expected: `title: "LMS Annual Membership"`, `handle: "basic"`, `tags` includes `"Supercycle product"`. If any of these don't match, STOP — this plan's later steps assume this exact product id is the stale one.

- [ ] **Step 2: Archive the product**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com --allow-mutations \
  --query 'mutation { productUpdate(product: { id: "gid://shopify/Product/8156540895294", status: ARCHIVED }) { product { id status } userErrors { field message } } }'
```

Expected: `"status": "ARCHIVED"`, empty `userErrors`.

- [ ] **Step 3: Leave its selling plan group in place**

Do not delete `gid://shopify/SellingPlanGroup/3221553214` — archiving the product detaches it from the storefront without needing a separate cleanup mutation, and deleting selling plan groups can be unpredictable if anything references it. Verify no dangling reference by re-running the query from Step 1 of Task 5 later and confirming it doesn't show up.

- [ ] **Step 4: Commit** (no file changes — this step is a note in case you're tracking progress in a commit; skip the actual `git commit` since nothing in the working tree changed)

---

## Task 2: Customer metafield definitions

Creates the two customer metafield definitions the Flow automation (Task 8) will write to: the Libib barcode and the member's birthday (needed year-round for the "free birthday movie" perk, not just visible on the signup order — see spec §4).

**Files:**
- Create: `scripts/create-membership-metafield-definitions.sh`

- [ ] **Step 1: Write the script**

```bash
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
```

- [ ] **Step 2: Make it executable and run it**

```bash
chmod +x scripts/create-membership-metafield-definitions.sh
./scripts/create-membership-metafield-definitions.sh
```

Expected: two `✓ custom.<key>: created` lines (or `=` lines if re-run).

- [ ] **Step 3: Verify via Admin API**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com \
  --query 'query { metafieldDefinitions(first: 10, ownerType: CUSTOMER) { nodes { namespace key type { name } } } }'
```

Expected: both `custom.libib_barcode` and `custom.birthday` present, both `single_line_text_field`.

- [ ] **Step 4: Commit**

```bash
git add scripts/create-membership-metafield-definitions.sh
git commit -m "$(cat <<'EOF'
feat: add membership customer metafield definitions script

Creates custom.libib_barcode and custom.birthday on the customer
resource — targets the Flow automation in Task 8 will write to.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VRbyadQRh8Dp676HijKtye
EOF
)"
```

---

## Task 3: Membership PDP template (terms checkbox + birthday capture)

Adds a dedicated product template for the membership product that captures terms acceptance and birthday as line-item properties, using Horizon's built-in `product-custom-property` block — no custom Liquid/JS needed. The checkbox uses a real `<input type="checkbox" required>` tied to the buy-buttons form, so "Add to cart" is blocked by the browser's native form validation even if JS fails (satisfies the spec's fail-closed requirement with zero custom code).

**Files:**
- Create: `theme/lms-redesign-v4/templates/product.membership.json`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: template suffix `membership`, consumed by Task 5 (product creation assigns this suffix).

- [ ] **Step 1: Create the template**

```json
{
  "sections": {
    "main": {
      "type": "product-information",
      "blocks": {
        "media-gallery": {
          "type": "_product-media-gallery",
          "static": true,
          "settings": {
            "media_presentation": "carousel",
            "media_columns": "two",
            "image_gap": 4,
            "large_first_image": false,
            "icons_style": "arrow",
            "slideshow_controls_style": "counter",
            "slideshow_mobile_controls_style": "dots",
            "thumbnail_position": "right",
            "thumbnail_width": 44,
            "thumbnail_radius": 0,
            "aspect_ratio": "adapt",
            "constrain_to_viewport": true,
            "media_fit": "contain",
            "media_radius": 0,
            "extend_media": false,
            "zoom": true,
            "video_loop": false,
            "hide_variants": true,
            "padding-block-start": 16,
            "padding-block-end": 16,
            "padding-inline-start": 16,
            "padding-inline-end": 16
          },
          "blocks": {}
        },
        "product-details": {
          "type": "_product-details",
          "static": true,
          "settings": {
            "width": "fill",
            "custom_width": 100,
            "width_mobile": "fill",
            "custom_width_mobile": 100,
            "height": "fit",
            "details_position": "flex-start",
            "gap": 28,
            "sticky_details_desktop": true,
            "background_media": "none",
            "video_position": "cover",
            "background_image_position": "cover",
            "border": "none",
            "border_width": 1,
            "border_opacity": 100,
            "border_radius": 0,
            "padding-block-start": 24,
            "padding-block-end": 24,
            "padding-inline-start": 0,
            "padding-inline-end": 0
          },
          "blocks": {
            "group_icgrde": {
              "type": "group",
              "name": "Header",
              "settings": {
                "content_direction": "column",
                "vertical_on_mobile": true,
                "horizontal_alignment": "flex-start",
                "vertical_alignment": "center",
                "align_baseline": false,
                "horizontal_alignment_flex_direction_column": "flex-start",
                "vertical_alignment_flex_direction_column": "center",
                "gap": 12,
                "width": "fill",
                "custom_width": 100,
                "width_mobile": "fill",
                "custom_width_mobile": 100,
                "height": "fit",
                "custom_height": 100,
                "background_media": "none",
                "video_position": "cover",
                "background_image_position": "cover",
                "border": "none",
                "border_width": 1,
                "border_opacity": 100,
                "border_radius": 0,
                "toggle_overlay": false,
                "overlay_color": "#00000026",
                "overlay_style": "solid",
                "gradient_direction": "to top",
                "link": "",
                "open_in_new_tab": false,
                "placeholder": "",
                "padding-block-start": 0,
                "padding-block-end": 0,
                "padding-inline-start": 0,
                "padding-inline-end": 0
              },
              "blocks": {
                "text_xrnftG": {
                  "type": "text",
                  "name": "Product title",
                  "settings": {
                    "text": "<h1>{{ closest.product.title }}</h1>",
                    "width": "100%",
                    "max_width": "normal",
                    "alignment": "left",
                    "type_preset": "h3",
                    "font": "var(--font-primary--family)",
                    "font_size": "",
                    "line_height": "normal",
                    "letter_spacing": "normal",
                    "case": "none",
                    "wrap": "pretty",
                    "text_color": "",
                    "background": false,
                    "background_color": "#00000026",
                    "corner_radius": 0,
                    "padding-block-start": 0,
                    "padding-block-end": 0,
                    "padding-inline-start": 0,
                    "padding-inline-end": 0
                  },
                  "blocks": {}
                },
                "price_tVjtKg": {
                  "type": "price",
                  "settings": {
                    "show_sale_price_first": true,
                    "show_installments": false,
                    "show_tax_info": false,
                    "type_preset": "paragraph",
                    "width": "100%",
                    "alignment": "left",
                    "font": "var(--font-body--family)",
                    "font_size": "1rem",
                    "line_height": "normal",
                    "letter_spacing": "normal",
                    "case": "none",
                    "padding-block-start": 4,
                    "padding-block-end": 0,
                    "padding-inline-start": 0,
                    "padding-inline-end": 0
                  },
                  "blocks": {}
                }
              },
              "block_order": [
                "text_xrnftG",
                "price_tVjtKg"
              ]
            },
            "divider_VJhene": {
              "type": "_divider",
              "name": "t:names.divider",
              "settings": {
                "thickness": 1,
                "corner_radius": "square",
                "width_percent": 100,
                "padding-block-start": 0,
                "padding-block-end": 0
              },
              "blocks": {}
            },
            "variant_picker_R3rGDr": {
              "type": "variant-picker",
              "settings": {
                "variant_style": "buttons",
                "show_swatches": false,
                "alignment": "left",
                "padding-block-start": 0,
                "padding-block-end": 0,
                "padding-inline-start": 0,
                "padding-inline-end": 0
              },
              "blocks": {}
            },
            "text_membership_terms_notice": {
              "type": "text",
              "name": "Membership terms notice",
              "settings": {
                "text": "<p>By purchasing, you agree to the <a href=\"/pages/membership-terms\">Little Movie Club Membership Agreement</a>.</p>",
                "width": "100%",
                "max_width": "normal",
                "alignment": "left",
                "type_preset": "paragraph",
                "font": "var(--font-body--family)",
                "font_size": "",
                "line_height": "normal",
                "letter_spacing": "normal",
                "case": "none",
                "wrap": "pretty",
                "text_color": "",
                "background": false,
                "background_color": "#00000026",
                "corner_radius": 0,
                "padding-block-start": 12,
                "padding-block-end": 0,
                "padding-inline-start": 0,
                "padding-inline-end": 0
              },
              "blocks": {}
            },
            "custom_property_terms_checkbox": {
              "type": "product-custom-property",
              "name": "Terms acceptance checkbox",
              "settings": {
                "property_heading": "",
                "property_description": "",
                "property_key": "Terms Accepted",
                "input_type": "checkbox",
                "max_length": 100,
                "checkbox_label": "I have read and agree to the Membership Agreement",
                "required": true,
                "placeholder": "",
                "placeholder_textarea": "",
                "padding-block-start": 12,
                "padding-block-end": 0,
                "padding-inline-start": 0,
                "padding-inline-end": 0
              },
              "blocks": {}
            },
            "custom_property_birthday": {
              "type": "product-custom-property",
              "name": "Birthday capture",
              "settings": {
                "property_heading": "Birthday",
                "property_description": "So we can give you a free movie every year, on us.",
                "property_key": "Birthday (MM/DD/YYYY)",
                "input_type": "text",
                "max_length": 25,
                "checkbox_label": "",
                "required": true,
                "placeholder": "MM/DD/YYYY",
                "placeholder_textarea": "",
                "padding-block-start": 12,
                "padding-block-end": 0,
                "padding-inline-start": 0,
                "padding-inline-end": 0
              },
              "blocks": {}
            },
            "buy_buttons_eYQEYi": {
              "type": "buy-buttons",
              "settings": {
                "stacking": true,
                "show_pickup_availability": false,
                "gift_card_form": false,
                "padding-block-start": 12,
                "padding-block-end": 0,
                "padding-inline-start": 0,
                "padding-inline-end": 0
              },
              "blocks": {
                "quantity": {
                  "type": "quantity",
                  "static": true,
                  "settings": {},
                  "blocks": {}
                },
                "add-to-cart": {
                  "type": "add-to-cart",
                  "static": true,
                  "settings": {
                    "style_class": "button"
                  },
                  "blocks": {}
                }
              },
              "block_order": []
            },
            "text_aEtTtq": {
              "type": "text",
              "name": "Product description",
              "settings": {
                "text": "{{ closest.product.description }}",
                "width": "100%",
                "max_width": "normal",
                "alignment": "left",
                "type_preset": "rte",
                "font": "var(--font-primary--family)",
                "font_size": "",
                "line_height": "normal",
                "letter_spacing": "normal",
                "case": "none",
                "wrap": "pretty",
                "text_color": "",
                "background": false,
                "background_color": "#00000026",
                "corner_radius": 0,
                "padding-block-start": 0,
                "padding-block-end": 0,
                "padding-inline-start": 0,
                "padding-inline-end": 0
              },
              "blocks": {}
            }
          },
          "block_order": [
            "group_icgrde",
            "divider_VJhene",
            "variant_picker_R3rGDr",
            "text_membership_terms_notice",
            "custom_property_terms_checkbox",
            "custom_property_birthday",
            "buy_buttons_eYQEYi",
            "text_aEtTtq"
          ]
        }
      },
      "settings": {
        "content_width": "content-center-aligned",
        "desktop_media_position": "left",
        "equal_columns": false,
        "limit_details_width": false,
        "gap": 48,
        "enable_sticky_add_to_cart": true,
        "padding-block-start": 64,
        "padding-block-end": 64
      }
    }
  },
  "order": [
    "main"
  ]
}
```

Note: `gift_card_form` is set to `false` here (unlike `product.retail.json`) since this product is never a gift card.

- [ ] **Step 2: Lint the theme**

```bash
shopify theme check --path theme/lms-redesign-v4
```

Expected: no new errors introduced by this file (pre-existing warnings elsewhere are not this task's concern).

- [ ] **Step 3: Push just this file to the dev store's live theme**

```bash
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 142364311614 --only templates/product.membership.json
```

- [ ] **Step 4: Commit**

```bash
git add theme/lms-redesign-v4/templates/product.membership.json
git commit -m "$(cat <<'EOF'
feat: add membership product template with terms + birthday capture

Uses Horizon's built-in product-custom-property block for both fields
instead of custom Liquid/JS: a required checkbox and a required text
field, both wired to the buy-buttons form via the same section.id the
theme already uses, so the browser's native form validation blocks
Add to cart until both are filled — fails closed without any JS.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VRbyadQRh8Dp676HijKtye
EOF
)"
```

(Verification that this actually renders and gates correctly happens in Task 5, once a product uses this template.)

---

## Task 4: Membership Terms page

Creates the `/pages/membership-terms` page the footer already links to (`sections/footer-group.json:149`) and the new PDP template links to. **The body copy here is a placeholder draft, not final legal text** — per the spec (§11), writing the actual agreement is explicitly out of scope for this build. This task's job is only to make the link resolve to a real, editable page instead of a 404.

**Files:**
- Create: `theme/lms-redesign-v4/templates/page.membership-terms.json`

- [ ] **Step 1: Create the template**

```json
{
  "sections": {
    "main": {
      "type": "main-page",
      "blocks": {
        "heading": {
          "type": "text",
          "name": "Title",
          "settings": {
            "text": "<h1>{{ closest.page.title }}</h1>",
            "width": "100%",
            "max_width": "normal",
            "alignment": "left",
            "type_preset": "h2",
            "font": "var(--font-primary--family)",
            "font_size": "",
            "line_height": "normal",
            "letter_spacing": "normal",
            "case": "none",
            "wrap": "pretty",
            "text_color": "",
            "background": false,
            "background_color": "#00000026",
            "corner_radius": 0,
            "padding-block-start": 0,
            "padding-block-end": 0,
            "padding-inline-start": 0,
            "padding-inline-end": 0
          },
          "blocks": {}
        },
        "body": {
          "type": "text",
          "name": "Body",
          "settings": {
            "text": "{{ closest.page.content }}",
            "width": "100%",
            "max_width": "normal",
            "alignment": "left",
            "type_preset": "rte",
            "font": "var(--font-body--family)",
            "font_size": "",
            "line_height": "normal",
            "letter_spacing": "normal",
            "case": "none",
            "wrap": "pretty",
            "text_color": "",
            "background": false,
            "background_color": "#00000026",
            "corner_radius": 0,
            "padding-block-start": 0,
            "padding-block-end": 0,
            "padding-inline-start": 0,
            "padding-inline-end": 0
          },
          "blocks": {}
        }
      },
      "block_order": [
        "heading",
        "body"
      ],
      "settings": {
        "content_direction": "column",
        "gap": 32,
        "padding-block-start": 40,
        "padding-block-end": 40
      }
    }
  },
  "order": [
    "main"
  ]
}
```

- [ ] **Step 2: Push this template**

```bash
shopify theme push --path theme/lms-redesign-v4 --store lms-sandbox-lutsfahz.myshopify.com --theme 142364311614 --only templates/page.membership-terms.json
```

- [ ] **Step 3: Create the actual Shopify page, with placeholder body content, and assign the template**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com --allow-mutations \
  --query 'mutation CreatePage($page: PageCreateInput!) { pageCreate(page: $page) { page { id handle templateSuffix } userErrors { field message } } }' \
  -v '{
    "page": {
      "title": "Membership Terms",
      "handle": "membership-terms",
      "isPublished": true,
      "templateSuffix": "membership-terms",
      "body": "<p><strong>DRAFT — pending final legal review. Do not treat this page as the binding membership agreement until this notice is removed.</strong></p><p>By enrolling in the Little Movie Club membership, you agree to an annual membership fee of $160, billed automatically each year unless cancelled. You may pause or cancel your membership at any time through your account. Membership benefits include a 10% discount on purchases and a free birthday movie each year, and are non-transferable.</p>"
    }
  }'
```

Expected: `userErrors` empty, `templateSuffix: "membership-terms"`.

- [ ] **Step 4: Verify in browser**

Visit `https://lms-sandbox-lutsfahz.myshopify.com/pages/membership-terms` (store password `Lms`) and confirm the heading and draft body render.

- [ ] **Step 5: Commit**

```bash
git add theme/lms-redesign-v4/templates/page.membership-terms.json
git commit -m "$(cat <<'EOF'
feat: add membership terms page template

Body content is an explicitly-marked draft pending legal review, not
final copy — see spec §11. This unblocks the footer link and the new
membership PDP's terms link from 404ing.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VRbyadQRh8Dp676HijKtye
EOF
)"
```

---

## Task 5: Create the Membership product

Creates the actual sellable product on the dev store using the template from Task 3.

**Files:** none (Admin API only).

**Interfaces:**
- Consumes: template suffix `membership` (Task 3), metafield definitions (Task 2, not written here yet — that happens in Task 8's Flow).
- Produces: a product id, referenced by Task 6 (selling plan attachment) and Task 8 (Flow condition).

- [ ] **Step 1: Create the product**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com --allow-mutations \
  --query 'mutation CreateProduct($product: ProductCreateInput!) { productCreate(product: $product) { product { id handle templateSuffix variants(first: 1) { nodes { id } } } userErrors { field message } } }' \
  -v '{
    "product": {
      "title": "Little Movie Club Membership",
      "descriptionHtml": "<p>A full year of access to our rental library. Renews automatically each year — pause or cancel anytime.</p>",
      "status": "ACTIVE",
      "templateSuffix": "membership",
      "tags": ["Membership"]
    }
  }'
```

Record the returned product `id` and the default variant `id` — both are needed in the next step and in Task 6.

- [ ] **Step 2: Set the variant price to $160.00**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com --allow-mutations \
  --query 'mutation SetPrice($productId: ID!, $variants: [ProductVariantsBulkInput!]!) { productVariantsBulkUpdate(productId: $productId, variants: $variants) { productVariants { id price } userErrors { field message } } }' \
  -v '{
    "productId": "<PRODUCT_ID_FROM_STEP_1>",
    "variants": [{ "id": "<VARIANT_ID_FROM_STEP_1>", "price": "160.00" }]
  }'
```

- [ ] **Step 3: Verify**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com \
  --query 'query { product(id: "<PRODUCT_ID_FROM_STEP_1>") { title templateSuffix status variants(first:1){nodes{price}} } }'
```

Expected: `title: "Little Movie Club Membership"`, `templateSuffix: "membership"`, `status: "ACTIVE"`, `price: "160.00"`.

- [ ] **Step 4: Visit the product page in browser and confirm the PDP renders correctly**

Visit `https://lms-sandbox-lutsfahz.myshopify.com/products/little-movie-club-membership` (store password `Lms`). Confirm:
- Title, $160.00 price, and description render.
- The terms notice paragraph with a working link to `/pages/membership-terms` appears.
- The terms checkbox and birthday text field both appear, both marked required.
- Clicking "Add to cart" without checking the box or filling birthday shows the browser's native "please fill out this field" / "please check this box" validation and does **not** add to cart.
- Checking the box, filling in a birthday, then clicking "Add to cart" succeeds and the cart shows both properties (Terms Accepted / Birthday (MM/DD/YYYY)) under the line item.

- [ ] **Step 5: No commit needed** (Admin API state change only, no repo files touched)

---

## Task 6: Shopify Subscriptions setup (manual admin runbook)

**This task is manual Shopify Admin configuration** — installing an app and building a selling plan through its UI isn't something the Admin API can do safely for you (the Shopify Subscriptions app manages some of its own bookkeeping behind its screens). Follow these steps exactly in the dev store's admin (`lms-sandbox-lutsfahz.myshopify.com/admin`).

- [ ] **Step 1: Confirm Shopify Payments is active on the dev store**

Admin → Settings → Payments. If Shopify Payments isn't enabled, POS subscription checkout will not work — stop and enable it (test mode is fine on a dev store) before continuing.

- [ ] **Step 2: Install the Shopify Subscriptions app**

Admin → Apps → search "Shopify Subscriptions" (published by Shopify) → Install.

- [ ] **Step 3: Create the selling plan group**

In the Shopify Subscriptions app: Add product → select "Little Movie Club Membership" (created in Task 5) → create a new selling plan:
- Name: `Yearly`
- Billing interval: every `1` `year`
- Auto-renew: on
- Price: full price (no discount from the selling plan itself — the 10% member discount is handled separately in Task 7, not via selling-plan pricing)

Save, and confirm the app shows the product with 1 active selling plan.

- [ ] **Step 4: Add a subscription cancellation policy**

Admin → Settings → Policies (or within the Shopify Subscriptions app settings, wherever the current Shopify UI surfaces it — this has moved between Shopify releases). Add a short cancellation policy, e.g.: "You may cancel your Little Movie Club membership at any time through your account. No refunds are provided for the remainder of a billing period already paid." This is required for POS eligibility (per Shopify's documented requirement).

- [ ] **Step 5: Add the Subscriptions tile to the POS smart grid**

Admin → Point of Sale → smart grid editor (or from the POS app itself: Smart Grid → Add tile → App → Shopify Subscriptions). Save.

- [ ] **Step 6: Customize the renewal-reminder email**

In the Shopify Subscriptions app: Settings → Customer notifications → find the "Upcoming order" (or "Upcoming payment") template. Edit it to use LMS branding (logo, brand colors from `assets/lms-tokens.css` — brick `#973123` / parchment `#fff9ef`) and confirm/set the number of days before renewal it sends. Send yourself a test email and confirm timing/content.

- [ ] **Step 7: Verify via Admin API**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com \
  --query 'query { product(id: "<PRODUCT_ID_FROM_TASK_5>") { sellingPlanGroups(first: 5) { nodes { name sellingPlans(first: 5) { nodes { name billingPolicy { ... on SellingPlanRecurringBillingPolicy { interval intervalCount } } } } } } } }'
```

Expected: one selling plan group named `Yearly` (or whatever you named it), one selling plan with `interval: YEAR, intervalCount: 1`.

- [ ] **Step 8: No commit needed** (admin configuration only)

---

## Task 7: Member discount (10% off, automatic)

Creates the customer segment and automatic discount for the member perk.

**Files:** none (Admin API only).

- [ ] **Step 1: Create the customer segment**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com --allow-mutations \
  --query 'mutation CreateSegment($name: String!, $query: String!) { segmentCreate(name: $name, query: $query) { segment { id name } userErrors { field message } } }' \
  -v '{ "name": "Active Member", "query": "customer_tags CONTAINS '\''Active Member'\''" }'
```

Record the returned segment `id`. If `userErrors` mentions invalid query syntax, check the exact segment query language against the current Shopify docs (`shopify-dev` skill → Admin GraphQL → customer segments) — the syntax above is correct as of this plan's writing but Shopify has changed this syntax across API versions before.

- [ ] **Step 2: Create the automatic discount**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com --allow-mutations \
  --query 'mutation CreateDiscount($discount: DiscountAutomaticBasicInput!) { discountAutomaticBasicCreate(automaticBasicDiscount: $discount) { automaticDiscountNode { id } userErrors { field message } } }' \
  -v '{
    "discount": {
      "title": "Active Member 10% off",
      "startsAt": "2026-09-13T00:00:00Z",
      "customerSelection": { "customerSegments": { "add": ["<SEGMENT_ID_FROM_STEP_1>"] } },
      "customerGets": {
        "value": { "percentage": 0.10 },
        "items": { "all": true }
      },
      "combinesWith": { "orderDiscounts": false, "productDiscounts": false, "shippingDiscounts": true }
    }
  }'
```

Expected: `userErrors` empty. Note: this does not need to exclude the membership product or gift cards — see Global Constraints above for why both are already non-issues.

- [ ] **Step 3: Verify**

```bash
shopify store execute --store lms-sandbox-lutsfahz.myshopify.com \
  --query 'query { automaticDiscountNodes(first: 5) { nodes { automaticDiscount { ... on DiscountAutomaticBasic { title status } } } } }'
```

Expected: `"title": "Active Member 10% off"`, `"status": "ACTIVE"`.

- [ ] **Step 4: No commit needed** (Admin API state change only)

---

## Task 8: Membership Flow automation (manual admin runbook)

**This task is manual Shopify Flow configuration** — building a multi-step workflow with conditional branches isn't something to hand-author as Admin API mutations; the Flow visual editor is the supported way to do this. Follow these steps exactly in Admin → Apps → Flow, on the dev store.

**Prerequisite:** obtain the Libib API key and API user value from the client's Libib account settings (Account → API, per Libib's docs) before starting. Do not proceed without both.

- [ ] **Step 1: Create a new workflow**

Flow → Create workflow. Name it `Membership signup → Libib + tag`.

- [ ] **Step 2: Add the trigger**

Trigger: `Subscription contract created`.

- [ ] **Step 3: Add a condition to scope this to the membership product only**

Condition: `Subscription contract > Line items > Product > ID` is `<PRODUCT_ID_FROM_TASK_5>`. (This future-proofs the workflow in case another subscription product is ever added — it won't misfire and create a Libib patron for it.)

- [ ] **Step 4: Add the tag action**

Action: `Add customer tag`. Tag: `Active Member`. Customer: the subscription contract's customer.

- [ ] **Step 5: Add the Libib HTTP request action**

Action: `Send HTTP request`.
- Method: `POST`
- URL: `https://api.libib.com/patrons`
- Headers:
  - `x-api-key`: `<the Libib API key obtained above>`
  - `x-api-user`: `<the Libib API user value obtained above>`
  - `Content-Type`: `application/json`
- Body (JSON, using Flow's data reference picker to insert the customer/contract fields — the bracketed names below are what you'll insert, not literal text):
```json
{
  "first_name": "{{customer first name}}",
  "last_name": "{{customer last name}}",
  "email": "{{customer email}}"
}
```

- [ ] **Step 6: Branch on the HTTP response status**

Add a `Condition` step: `HTTP response status code` is between `200` and `299`.

**If true (success path):**
- Action: `Set customer metafield` — namespace `custom`, key `libib_barcode`, value: the `barcode` field from the HTTP response JSON (Flow's response is available as structured JSON you can reference field-by-field after this step).
- Action: `Set customer metafield` — namespace `custom`, key `birthday`, value: the `Birthday (MM/DD/YYYY)` line-item property from the subscription contract's originating order (Flow exposes order line-item properties as a data reference).

**If false (failure path) — first retry:**
- Action: `Wait` — 30 seconds.
- Action: repeat the same `Send HTTP request` from Step 5 (Flow lets you duplicate a step).
- Action: `Condition` on the retry's response status, same 200-299 check.
  - **If true:** same two `Set customer metafield` actions as the success path above.
  - **If false (final failure):** `Add customer tag` — tag `Libib Sync Failed` — so staff can create the patron manually in Libib and remove this tag once resolved. Do **not** add any action that blocks, cancels, or refunds the subscription contract — the sale stands regardless of Libib's availability (per spec §5).

- [ ] **Step 7: Turn the workflow on**

Toggle the workflow from Draft to On.

- [ ] **Step 8: Test it**

In the dev store admin, manually trigger a test: Flow → this workflow → "Run test" if available, or complete a real test membership purchase (this is covered more fully in Task 10, but do at least one dry run here to confirm the workflow doesn't error out on its own logic before moving on). Check:
- The test customer gets tagged `Active Member`.
- A patron actually appears in the real Libib account (remember: no sandbox — delete this test patron from Libib afterward).
- `custom.libib_barcode` and `custom.birthday` are populated on the test customer (`shopify store execute --query 'query { customer(id: "<id>") { metafield(namespace: "custom", key: "libib_barcode") { value } } }'`).

- [ ] **Step 9: No commit needed** (Flow workflows live in Shopify Admin, not the repo)

---

## Task 9: Email blast capability (Shopify Email)

Confirms the client can send a campaign to all members, per spec §8. This is store-owner-facing setup, not something the client needs an agent to operate on their behalf going forward — this task just proves the segment targeting works.

**Files:** none (Admin configuration + verification only).

- [ ] **Step 1: Confirm Shopify Email is installed**

Admin → Apps → search "Shopify Email" (published by Shopify). Install if not already present (it's free and commonly pre-installed).

- [ ] **Step 2: Create a test campaign targeting the Active Member segment**

Admin → Marketing → Create campaign → Email → Shopify Email. Set the audience to the `Active Member` segment created in Task 7, Step 1. Use any placeholder subject/content — this is a targeting test, not a real send.

- [ ] **Step 3: Verify segment targeting**

Confirm the campaign's audience count matches the number of customers currently tagged `Active Member` (check via Admin → Customers → filter by tag `Active Member` and compare counts). Do not actually send the test campaign — discard it once the count is confirmed.

- [ ] **Step 4: No commit needed** (Admin configuration only)

---

## Task 10: POS staff terms-acceptance checklist

Per the brainstorming decision, POS terms capture is the free manual process (order note), not the paid TnC app. This task writes down the staff script so it's actually followable at the register, not just implied.

**Files:**
- Create: `docs/pos-membership-terms-checklist.md`

- [ ] **Step 1: Write the checklist**

```markdown
# POS: Selling a Little Movie Club Membership

Follow every step, in order, for every in-person membership sale.

1. Tell the customer the membership is $160/year, auto-renews yearly, and
   they can pause or cancel anytime through their online account.
2. Hand them the printed Membership Agreement (or read it aloud) — same
   text as littlemoviestore.com/pages/membership-terms.
3. Ask for their verbal agreement to the terms.
4. Ask for their birthday (for the free birthday movie perk).
5. Before completing the sale, open the order note field on the POS order
   and type exactly:
   `Terms agreed - verbal. Birthday: <MM/DD/YYYY>`
6. Add the Little Movie Club Membership product (via the Subscriptions
   smart grid tile) and complete the sale.
7. Confirm with the customer that they'll get a confirmation email.

If the POS order note field is skipped, there is no record this customer
agreed to the terms or provided a birthday — the sale should not be
completed without it.
```

- [ ] **Step 2: Commit**

```bash
git add docs/pos-membership-terms-checklist.md
git commit -m "$(cat <<'EOF'
docs: add POS membership terms-acceptance staff checklist

Free manual-process path chosen over the ~\$8/mo TnC POS app during
brainstorming — this is the staff-facing script that makes that
process actually followable at the register.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VRbyadQRh8Dp676HijKtye
EOF
)"
```

---

## Task 11: End-to-end testing

Runs the full spec's testing plan (§10) against everything built in Tasks 1-9. All on the dev store.

**Files:** none (manual verification).

- [ ] **Step 1: Online test purchase**

Visit the membership PDP, check the terms box, enter a birthday, add to cart, complete checkout with a test card. Verify:
- Order shows both line-item properties under "Additional details".
- Within a few minutes, the Flow-tagged customer has `Active Member` tag (Admin → Customers → search the test customer).
- `custom.libib_barcode` and `custom.birthday` are populated on the customer.
- A patron exists in the real Libib account matching this test purchase.
- Placing a second, separate test order (any product) as this now-tagged customer shows the 10% discount applied automatically.

- [ ] **Step 2: POS test purchase**

Using a POS device signed into the dev store, follow `docs/pos-membership-terms-checklist.md` exactly for a second test customer. Verify the same downstream effects as Step 1 (tag, Libib sync, metafields, discount on a follow-up sale).

- [ ] **Step 3: Induced Libib failure test**

Temporarily change the Flow workflow's HTTP request URL (Task 8, Step 5) to an invalid endpoint (e.g. `https://api.libib.com/does-not-exist`), run a third test purchase, and verify:
- The sale completes normally (contract created, no block/refund).
- After the retry, the customer ends up tagged `Libib Sync Failed`.
- No Libib patron was created (nothing to clean up in Libib for this one).

Revert the URL back to `https://api.libib.com/patrons` afterward and re-verify Step 8's dry run still succeeds.

- [ ] **Step 4: Pause/cancel test**

As one of the test customers from Step 1 or 2, go to the customer account portal (`shopify.com/<shop-id>/account`, per Global Constraints), find the subscription, and test both Pause and Cancel. Verify each takes effect (Admin → Customers → that customer → Subscriptions shows the updated status).

- [ ] **Step 5: Confirm renewal-reminder content and timing**

Re-check the test email sent in Task 6, Step 6 — confirm branding, copy, and the days-before-renewal timing all look right for a real member to receive.

- [ ] **Step 6: Confirm email-blast targeting still holds with real test members**

Re-run Task 9's segment-count check now that Steps 1-2 have created real `Active Member`-tagged test customers — confirm the count increased correctly and both test customers appear in the segment.

- [ ] **Step 7: Clean up test data**

- Delete all test patrons created in Libib during Steps 1-3.
- Cancel/archive the test subscription contracts and orders in Shopify admin (or leave them — dev store test data is low-stakes, but note in your summary to the user which test orders/customers exist so they can decide).

- [ ] **Step 8: No commit needed** (verification only)

---

## Task 12: Fix the stale theme ID in CLAUDE.md

Small housekeeping so the next person (or agent) doesn't repeat the wrong-theme mistake this plan caught during research.

**Files:**
- Modify: `CLAUDE.md` (the "Working theme on dev store" table)

- [ ] **Step 1: Update the table**

Change the row currently reading:
```
| Working theme (v4) | `140918915134` | Current push/pull target on `lms-sandbox-lutsfahz.myshopify.com` |
```
to:
```
| Working theme (v4) | `142364311614` | **Live/MAIN** theme on `lms-sandbox-lutsfahz.myshopify.com` (verified 2026-09-13; `140918915134` is unpublished and stale as a reference) |
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: correct stale dev-store theme ID in CLAUDE.md

140918915134 is unpublished; the dev store's actual live theme is
142364311614, discovered while building the membership system
(docs/superpowers/plans/2026-09-13-membership-system-implementation.md).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VRbyadQRh8Dp676HijKtye
EOF
)"
```
