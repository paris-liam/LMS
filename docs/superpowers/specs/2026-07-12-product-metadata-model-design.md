# Product Metadata Model — Design Spec

**Date:** 2026-07-12
**Status:** Approved (pending final spec review)
**Scope:** How movie products and their metadata are modelled in Shopify for the LMS storefront — metafield definitions, native-field usage, curation, and the boundary with Supercycle-owned data. This is a **fresh** model; it supersedes the ad-hoc `custom.director` / `custom.format` / `custom.condition` / `custom.rare` fields the theme reads today.

---

## Goals

- Model everything a curated physical-media shop needs on a movie: descriptive film facts, physical/commerce attributes, curation, and storefront facets.
- **Balance efficient setup with client ease-of-use** when uploading/editing products.
- Never collide with Supercycle: no `supercycle.*` namespace, and no duplication of data Supercycle already owns per physical copy.
- Stay **migration-ready**: flat metafields now, shaped so shared "film" data can lift into a Film metaobject later without a rewrite.

## Key decisions (from brainstorming)

1. **One Shopify product = one physical listing** (per format/copy), not one-product-per-film. Each listing is self-contained.
2. **Duplication is left open.** Same film in multiple formats is possible but its frequency is unknown, so we model **flat `custom.*` metafields now**, named/grouped so they migrate cleanly into a `custom.film` metaobject if duplication becomes painful.
3. **Genre** = controlled checklist (defined-choice list metafield), not free tags, not a metaobject.
4. **Format** = `custom.format` single-select metafield (not Shopify Category/Type) for full facet control.
5. **Condition is split** (see Layer 4): Supercycle owns per-copy condition for serialized rental/resale stock; a `custom.media_condition` field exists **only** for new-sealed retail movies that have no Supercycle item.
6. **Storefront facets:** Format, Genre, Decade, Label/Distributor (one facet, not two) — plus Supercycle availability on a separate track.

## Research basis (Supercycle data model)

Confirmed via the `supercycle-builders-mcp` docs:

- Supercycle tracks each **physical copy as a serialized `item`** with its own **condition** (Supercycle's own grading — unused/used/refurbished, severity/title), serial, location, and availability.
- Rental/resale/membership **methods attach at the Shopify variant level** (`supercycle.methods`, `*_configuration` metafields; membership credit cost per variant; items carry `shopifyVariantId`).
- Therefore **condition/quality for anything rentable or resale is already owned by Supercycle per-copy** — modelling it again as a product metafield would duplicate and risk confusion. It is deliberately excluded from Layers 1–2 for serialized stock.

---

## The model

### Layer 0 — Native Shopify fields (use these; do not reinvent)

| Data | Lives in | Rationale |
|---|---|---|
| Title | Product title | — |
| **Synopsis / description** | Product **Description** (body) | Native rich text, SEO-indexed. No metafield. |
| Cover art / stills | Product images | Native. |
| Price / stock | Variant price + inventory | Supercycle layers rental/resale on top of this. |
| **Catalogue class** (Movie / Apparel / Snack / Art / Gift card) | Product **Category** (Shopify Standard Taxonomy) + Type | Powers other sales channels + broad collections. Movies → "Media". Distinct from `custom.format`, which is the disc format *within* movies. |

### Layer 1 — Film facts (`custom.*`) — the "film layer" (future metaobject candidate)

| Key | Type | Facet | Notes |
|---|---|---|---|
| `custom.director` | `single_line_text_field` | — | Display only |
| `custom.year` | `number_integer` | — | Drives decade |
| `custom.decade` | `single_line_text_field`, **defined choices** (`1950s`…`2020s`, plus `Pre-1950`) | ✅ | Facet-friendly bucket. Can be auto-filled from `year` via Shopify Flow (see Open Items). |
| `custom.country` | `single_line_text_field` | — | Co-productions: single value for v1 (see Open Items). |
| `custom.runtime` | `number_integer` (minutes) | — | Display as e.g. "142 min". |
| `custom.genres` | `list.single_line_text_field`, **defined choices** | ✅ | Multi-select checklist. Controlled vocabulary to keep the facet clean. |

### Layer 2 — Copy / commerce (`custom.*`) — stays on the product

| Key | Type | Facet | Notes |
|---|---|---|---|
| `custom.format` | `single_line_text_field`, defined choices (`Blu-ray`, `DVD`, `4K UHD`, `VHS`, extendable) | ✅ | The client's "product type". |
| `custom.label` | `single_line_text_field`, defined choices (`Criterion`, `A24`, `Arrow`, `Kino Lorber`, extendable) | ✅ | Surfaced as the **"Label / Distributor"** facet (one axis, confirmed). |
| `custom.media_condition` | `single_line_text_field`, defined choices (`Sealed / New`, `Like New`, `Good`, `Fair`) | — | **Non-Supercycle retail stock only.** Serialized rental/resale copies use Supercycle's per-item condition (Layer 4). Theme display rule: if a Supercycle item condition exists, show that; else fall back to `custom.media_condition`. |
| `custom.staff_pick_note` | `multi_line_text_field` | — | Staff blurb shown on card/PDP. Presence pairs with the `staff-pick` curation tag (Layer 3). |

### Layer 3 — Curation via tags (drive automated Collections; fast bulk-edit)

Simple curation buckets are **product tags**, each backing an **automated Collection**:

- `staff-pick` — pairs with `custom.staff_pick_note`. The tag drives the "Staff Picks" collection; the note supplies the copy.
- `rare` — "Rare Finds" collection (replaces the old `custom.rare` boolean).
- `holiday` and other seasonal/special buckets — one tag → one automated Collection each.

These are **not** storefront facets (per the facet decision), so tags — the fastest thing to bulk-apply and the native driver for automated collections — are the right tool rather than metafields.

### Layer 4 — Supercycle-owned (do NOT model in `custom.*`)

- Per-copy **condition, serial, location, availability** → Supercycle `item`.
- **Methods**: `supercycle.methods` and the `*_configuration` metafields are Supercycle-written; the theme only **reads** them.
- The **availability facet** ("available now") comes from Supercycle — the Methods filter app block or a smart collection (feature-plan Feature 1) — a separate track from this schema.
- **Never** hand-create the `supercycle` namespace.

---

## Facet set (Shopify Search & Discovery)

Define together, in one filter set: **Format**, **Genre**, **Decade**, **Label / Distributor**, plus **Supercycle availability** (added on the Feature 1 track). Defining them together avoids piecemeal filter drift.

## Client upload ergonomics

- Every attribute is a metafield with **defined choices** (dropdowns/checklists) or a tag — minimal free typing, fewer inconsistencies.
- Synopsis uses the **native Description** field the client already knows.
- Curation is **tag-based** bulk editing.
- The entire model is **CSV-importable** (metafield columns + tags column) — a concrete reason to stay flat rather than adopt metaobjects now (metaobjects are clumsy in CSV import).
- **Admin polish:** pin a "Movie" metafield group/template on the product page so all Layer 1–2 fields appear in one panel in the order above.

## Migration path (flat → Film metaobject)

Layer 1 (`director`, `year`, `decade`, `country`, `runtime`, `genres`) plus the native Description is exactly the set that would move into a `custom.film` metaobject referenced from each product, if the same film routinely appears as multiple products and duplication becomes costly. Layer 2 (copy/commerce), Layer 3 (curation), and Layer 4 (Supercycle) stay on the product. Field names are chosen so the migration is find-and-replace (`custom.director` → `custom.film.value.director`, etc.).

## Impact on existing theme code

The theme currently reads:
- `custom.director` — **unchanged** (kept).
- `custom.format` — **unchanged** (kept, now backed by defined choices).
- `custom.condition` — **repoint** to `custom.media_condition` + Supercycle item condition fallback.
- `custom.rare` (boolean) — **replace** with the `rare` tag.

Files known to touch these (repoint during implementation): `snippets/lms-product-card.liquid` (and any PDP/disclosure blocks that read the old keys).

## Open items (resolve during planning/implementation)

1. **Country co-productions** — single-line for v1; revisit `list.single_line_text_field` if multi-country display is wanted.
2. **Decade auto-fill** — decide manual dropdown vs a Shopify Flow that derives `custom.decade` from `custom.year` (removes a client step; adds a Flow to maintain).
3. **Defined-choice maintenance** — adding a new genre/label value = editing the metafield definition's choices (occasional admin task). If either vocabulary churns heavily, revisit a metaobject for that field.
4. **Definition ownership** — these are **merchant-owned** `custom.*` definitions created in the Shopify Admin (or via Admin API against the dev store), not app TOML. The `shopify-custom-data` app-developer guidance (TOML, `$app` namespace) does **not** apply here.
5. **Category value** — confirm the exact Shopify Standard Taxonomy node for movies ("Media > …") at implementation.

## Out of scope

- Availability facet / "available now" logic (Supercycle Feature 1 track).
- Serialized-item creation, resale condition pricing, rental methods config (Supercycle admin).
- Non-movie retail catalogue attributes (apparel/snacks/art) beyond the shared Category/Type field.
