# Setting up Events & Staff Picks content

Both homepage sections read from **merchant-managed metaobjects** via `shop.metaobjects.*` in Liquid — this is set up entirely in Shopify Admin (Settings → Custom data), not via app code.

## 1. `event` metaobject — powers "Events & screenings" (`sections/lms-events-membership.liquid`)

**Admin → Settings → Custom data → Metaobjects → Add definition**

| Setting | Value |
|---|---|
| Name | `Event` |
| Type (handle) | `event` — must match exactly, the Liquid calls `shop.metaobjects.event` |

Fields to add, in this order:

| Field name | Key (must match) | Type |
|---|---|---|
| Name | `name` | Single line text |
| Date | `date` | Date |
| Description | `description` | Single line text |
| Audience | `audience` | Single line text — add **validation → choose from a list** with options `Members`, `Public` (drives the badge color) |
| Link | `link` | URL (optional) |

**Critical:** enable **Storefront access** on this definition (toggle near the top of the definition editor) — without it, `shop.metaobjects.event` returns nothing and the section shows the "No upcoming events yet" empty state.

**Adding entries**: Admin → Content → Events → Add entry. Fill in Name/Date/Description/Audience/Link, Save. Repeat per event.

Notes:
- The section auto-sorts by soonest upcoming date and hides past events — you don't need to order entries manually.
- `events_to_show` in the section settings (2–5) caps how many render.
- Section setting `events_link` should point to your full events/calendar page once you have one (currently blank).

## 2. `staff_pick` metaobject — powers "Staff picks" (`sections/lms-staff-picks.liquid`)

**Admin → Settings → Custom data → Metaobjects → Add definition**

| Setting | Value |
|---|---|
| Name | `Staff pick` |
| Type (handle) | `staff_pick` |

Fields:

| Field name | Key | Type |
|---|---|---|
| Product | `product` | Product reference |
| Quote | `quote` | Multi-line text |
| Staff name | `staff_name` | Single line text |

Enable **Storefront access** here too.

**Adding entries**: Admin → Content → Staff picks → Add entry → pick a product, write the shelf-note quote, add the staff member's name, Save.

Notes:
- Poster image, title, and link all come from the referenced product automatically — no separate image upload.
- Entries render in the order the metaobject list returns them (creation order by default) — reorder by editing/recreating if you need a specific sequence, since there's no drag-reorder for metaobject entries in Admin.
- `picks_to_show` (2–4) caps how many render; set `link` to a full staff-picks page if/when one exists.

## Suggested order of operations
1. Create both metaobject definitions with Storefront access enabled (5 min).
2. Add 3–5 real events and 4+ staff picks as content.
3. In the theme editor, confirm the two homepage sections settings (`events_to_show`, `picks_to_show`, link labels) match what you want shown.
4. Reload the homepage — the sections pull live once entries exist; no template/schema changes needed.

## Open follow-up
Consider scaffolding a dedicated `/pages/events` or `/pages/staff-picks` listing template so the "All events →" / "Full list →" links go somewhere real, instead of `#`.
