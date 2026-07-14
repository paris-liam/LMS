# Homepage Events + Shop/Membership Rework — Design Spec

**Date:** 2026-07-14
**Status:** Approved (pending final spec review)
**Scope:** Items 2 and 3 from `NOTES 7-14.md` — retiring the events+membership split tile in favor of a shop/membership split tile, and moving events out to their own full-width section plus a dedicated Events page. Items 1 and 4 from the same notes (hero/header tweaks, community picks) were simple and already implemented directly (see git history 2026-07-14).

---

## Goals

- Replace the current events+membership homepage tile with a shop(online-store)+membership tile, without touching the membership logic.
- Give events their own full-width homepage presence and a dedicated page with the complete upcoming calendar.
- Never delete retired section files (`lms-events-membership.liquid`, `lms-promo-pair.liquid`) — only remove their instances from the homepage template, per the client's notes.
- Avoid tripling the existing (fragile) event date-sort logic across three places.

## Current state (relevant files)

- `sections/lms-events-membership.liquid` — split card: events list (left, next N upcoming from the `event` metaobject) + membership panel (right: member card, perks blocks, price, join button).
- `sections/lms-promo-pair.liquid` — thin `@theme`-block container currently seeded with two `lms-promo-card` blocks (rental library, mystery bag) on the homepage.
- `sections/lms-new-releases.liquid` — reference pattern for a `collection`-setting-driven product grid (merchant picks the collection; no hardcoded handle).
- `templates/index.json` — homepage section order: `lms_hero, lms_ticker, lms_new_releases, lms_events_membership, lms_promo_pair, lms_staff_picks, lms_newsletter_3dYbxn, lms_social_bar_fiYNVL`.
- The `event` metaobject (Admin → Content) has fields `name`, `date`, `description`, `audience` (Members|Public), `link`. Sort logic in `lms-events-membership.liquid` works around metaobject value lists not being reliably index-able: it renders each event's markup into a `capture`, prefixes it with its ISO date, joins with a split-friendly delimiter, and sorts the resulting strings (ISO dates sort correctly as strings).

## Key decisions (from brainstorming)

1. **New section, not a rewrite:** `lms-shop-membership.liquid` is a new file. `lms-events-membership.liquid` is left in the repo, unused, per the client's explicit "do not delete" instruction.
2. **Shop panel uses a `collection` setting**, matching `lms-new-releases`'s pattern — no hardcoded `online-store` handle, so the merchant can repoint it later. 2×2 poster grid (4 products), "Shop now →" link derived from `collection.url` (not a separate URL setting — one less thing to keep in sync).
3. **Membership panel is copied verbatim** from `lms-events-membership.liquid` — same settings IDs, same blocks (`perk`), same markup/classes. No behavior change.
4. **Events get their own full-width section**, `lms-events-full.liquid`, replacing the `lms-promo-pair` instance on the homepage (file kept, instance removed). Card-row layout: date block + name + audience badge, no description (space-constrained, scannable-first). Configurable count via `events_to_show` range setting, default 4.
5. **Shared sort logic extracted** into `snippets/lms-events-list.liquid`, parameterized by:
   - `limit` — integer, or blank/0 for unlimited
   - `style` — `"cards"` (full-width homepage section) or `"rows"` (dedicated Events page, matches today's list-row look: date + name + description + badge)
   This is the one piece of genuine complexity being touched (the string-sort workaround); centralizing it means the next new consumer doesn't re-implement it a third time. `lms-events-membership.liquid` is **not** refactored to use the snippet — it's retired/unused, not worth the risk of touching working code we're about to orphan.
6. **New Events page**: `sections/lms-events-calendar.liquid` (renders `lms-events-list` with `style: "rows"`, `limit: 0`) inside a new `templates/page.events.json`. Filter stays "upcoming only" (`event_date >= today`), consistent with today's behavior — no past-events archive.
7. **Page record creation is a manual step.** Creating the actual "Events" Page resource in Admin and assigning it the `events` template suffix requires write access the CLI's current store-auth token doesn't have (confirmed earlier this session: `metaobjectDefinitionUpdate` returned `RECORD_NOT_FOUND` despite `--allow-mutations`, and the `menus` query returned `ACCESS_DENIED` — the token is read-heavy/theme-scoped). This will be flagged as a follow-up, consistent with the nav-menu-link and metaobject-field follow-ups from earlier today.

---

## Component 1 — `sections/lms-shop-membership.liquid`

**Layout:** identical shell to `lms-events-membership.liquid` — `.lms-split-section` > `.lms-split` (2-col bordered card, sunken parchment background, stacks to 1-col under 990px). Left panel class renamed `.lms-split__shop` (was `.lms-split__events`); right panel `.lms-split__membership` unchanged.

**Left panel (shop showcase):**
- Eyebrow + heading + optional description (settings: `shop_eyebrow`, `shop_heading`, `shop_description`) — text only, no rich copy needed beyond a short line.
- `collection` setting (`shop_collection`) — same picker pattern as `lms-new-releases`.
- 2×2 grid of up to 4 products from that collection, each rendered via the existing `lms-product-card` snippet (reuse, don't reinvent) OR a lighter poster-only treatment if `lms-product-card` pulls in price/add-to-cart chrome that doesn't fit a small tile — **decision: reuse `render 'lms-product-card', card_product: product` as-is**, same as `lms-new-releases` does, for visual consistency across the storefront rather than inventing a second card style.
- "Shop now →" link, `href="{{ collection.url }}"`, using the same `.lms-split__textlink` class as today's "All events →" link, hidden if no collection selected. If no collection is selected, the poster grid renders `lms-new-releases`'s placeholder-card onboarding pattern (four "Example title" placeholder tiles) — same precedent, not a bespoke empty state.

**Right panel (membership):** unchanged copy of today's `.lms-split__membership` block — eyebrow, heading, member card (brand/est/holder name), `perk` blocks (unchanged block type/schema), price, join button. Settings IDs (`membership_eyebrow`, `membership_heading`, `card_est_text`, `card_name_text`, `price_text`, `price_suffix`, `button_label`, `button_link`) carried over unchanged so the existing homepage values in `templates/index.json` can be copied across directly.

**Schema:** `name: "LMS shop + membership"`, `class: "lms-shop-membership-section"`, same `perk` block type/`max_blocks: 6`, same section-style (background color + padding) settings as every other LMS section.

## Component 2 — `sections/lms-events-full.liquid`

**Layout:** full-width container (`.lms-container`), eyebrow/heading row (settings: `eyebrow`, `heading`, default "Coming up" / "Events & screenings" — carried over from today's events copy), optional "All events →" link to the new Events page, then a horizontal row of event cards below.

**Card style** (rendered via `render 'lms-events-list', limit: section.settings.events_to_show, style: 'cards'`):
- Each card: month/day date block (reusing `.lms-events__month` / `.lms-events__day` treatment), event name (links out if `event.link.value` present), audience badge (`.lms-badge--brick` / `.lms-badge--sage`, same logic as today). No description — the card format is a scannable strip, not a dense list.
- Grid: `repeat(4, 1fr)` desktop, collapsing to horizontal scroll-snap on mobile (same responsive pattern as `lms-new-releases__grid`).

**Schema settings:** `eyebrow`, `heading`, `events_to_show` (range, min 2 max 8, default 4), `all_events_link_label` (default "All events →"), `all_events_link` (URL — will be set to `/pages/events` in the homepage template once the page exists), plus standard section-style settings (background color, padding).

## Shared snippet — `snippets/lms-events-list.liquid`

**Params:** `limit` (integer; 0 or blank = unlimited), `style` (`"cards"` | `"rows"`).

**Behavior:** ports the existing collect/filter/sort logic verbatim from `lms-events-membership.liquid` (today → date compare → capture per-event HTML → ISO-date-prefixed sortable string → split + sort). The only change: the per-event markup capture branches on `style` to emit either the card markup (Component 2's look) or the row markup (today's exact list-item look: date block + name + description + badge, used by both the legacy section's visual style and the new Events page). Also handles the empty state (no upcoming events) per style, matching today's copy ("No upcoming events yet...").

## New page — Events

**`sections/lms-events-calendar.liquid`:** simple wrapper — eyebrow/heading settings (default "Events & screenings" or similar — client hasn't specified page copy, so defaults will read reasonably and are editable), then `render 'lms-events-list', limit: 0, style: 'rows'`.

**`templates/page.events.json`:** standard page template referencing the section above (plus whatever default `main-page`/header content Horizon page templates normally include — following the pattern of existing page templates in this theme, e.g. `page.membership.json`).

**Follow-up (manual, like the nav-link and metaobject-field items):** create the "Events" page in Admin → Online Store → Pages, assign it the `events` template.

## Homepage template changes (`templates/index.json`)

- Remove `lms_events_membership` and `lms_promo_pair` from `order` (and can leave their config blocks in place, unreferenced — matches "kept but unused" spirit, though removing the now-dead blocks entirely is also fine; **decision: remove both from `order` and delete their now-dead entries from `sections`**, since `templates/index.json` is the *live homepage instance data*, not the retired section *files* the notes are protecting).
- Add `lms_shop_membership` (type `lms-shop-membership`) in the vacated slot, with `shop_collection` set to the `online-store` collection, membership settings copied from the old `lms_events_membership` entry, and 4 `perk` blocks copied across unchanged.
- Add `lms_events_full` (type `lms-events-full`) in the vacated slot, with `events_to_show: 4`, eyebrow/heading copied from the old `lms_events_membership` entry, and `all_events_link: "/pages/events"`.

## Testing / validation

- `shopify theme check` after each file addition — watch for the existing baseline (9 offenses / 2 errors, pre-existing Supercycle block warnings) and confirm no new offenses.
- Manually preview homepage + new Events page via `shopify theme dev` (run by the user interactively — the CLI prompts for the storefront password, which fails non-interactively) to confirm: shop panel renders products from the `online-store` collection, membership panel is visually/functionally identical to before, events full-width section shows the right N events in date order, Events page shows the complete upcoming list.
- No automated test suite exists in this theme repo (Liquid theme, not an app) — validation is theme-check + manual preview, consistent with how prior work in this repo has been verified.

## Open items / assumptions carried into the plan

- Events page copy (eyebrow/heading) has no client-specified text — using sensible defaults, editable in the theme editor.
- "Shop now" link derives from the collection URL rather than being a separate settable URL — simpler, one less field to keep in sync, matches `lms-new-releases` precedent.
- Product card in the shop panel reuses `lms-product-card` snippet as-is (same as `lms-new-releases`) rather than a bespoke poster-only treatment, for visual consistency across the site.
