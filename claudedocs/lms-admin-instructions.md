# LMS admin instructions (running doc)

How-to instructions for content the client (or whoever's running day-to-day admin) needs to manage in Shopify Admin. Built up section by section as we work through the site audit — see `claudedocs/2026-08-28-dev-site-audit-checklist.md` for the full punch list this is drawn from.

Everything below currently describes the **dev store** (`lms-sandbox-lutsfahz.myshopify.com`). Each section notes what still needs to happen on **production** (`p0wkgv-wy.myshopify.com`) before these instructions apply there too.

---

## Navigation — 2 broken links to fix manually

Found while checking the main and footer menus. Both are quick manual fixes in Admin → Online Store → Navigation — I didn't fix these via the API because the mutation that edits a menu replaces its *entire* item list in one call, and getting one item's type wrong on that full-replace risks wiping the whole menu. Safer done by hand.

- **Main menu → "Events"** currently links to `/pages/data-sharing-opt-out` (the auto-generated privacy page) instead of `/pages/events`. Almost certainly a mis-click when the menu was set up. Fix: Admin → Online Store → Navigation → Main menu → click "Events" → change the link to Pages → events.
- **Footer → "Visit" column → "Passyunk Ave, Philly" and "Hours & map"** both link to `/pages/visit`, which doesn't exist as a page at all (confirmed in Admin — no page with that handle). Either create a real "Visit" page with the address/hours content, or repoint these links to wherever that content actually lives.

---

## Footer links — flagged for review (not fixed, needs a content decision)

Three separate footer issues turned up during the audit. None are fixed — they need someone (client or you) to decide on real destinations, not a code fix.

- **4 broken collection links** (from the P0 audit): the footer's Shop and Visit columns link to `/collections/4k-blu-ray`, `/collections/used-vhs`, `/collections/mystery-bags`, and `/collections/rental-library` — none of these collections exist on the dev store, so all four 404. Decision at the time was not to fix as part of the initial pass; worth a deliberate look before launch — either create these collections or point the links elsewhere.
- **Footer "The Club" column**: all four links ("Join the club," "Member perks," "Borrow buddy," "Refer a friend") currently point to the exact same URL, `/pages/membership`. May be an intentional placeholder (one page covers all of it for now) or may have been meant as distinct anchors/pages — confirm intent.
- **Footer social links use generic root URLs, not real handles**: TikTok → `https://www.tiktok.com/`, Threads → `https://www.threads.net/` (Instagram is correctly set to the real profile). The homepage social bar has the same two blank instead of pointing anywhere. Neither location currently sends visitors to a real LMS TikTok/Threads profile.
- **Hero background image** (`Screenshot_2026-07-02_at_9.56.45_PM.png`): resolves fine on Shopify's CDN, but the filename suggests it may be a placeholder screenshot rather than finished art. Confirm with whoever built the hero before launch.

---

## New Arrivals (homepage "New arrivals this week" rail)

### How it works

The homepage section reads a fixed smart collection, handle `new-arrivals`. A product shows up there automatically the moment it matches **all three** conditions, and drops out the moment any one stops being true:

> Category = Videos **and** tagged `Rental` **and** tagged `new-arrival`

No one ever edits this collection directly — it's rule-driven.

### Decision: tagging is manual, not automatic

We considered auto-tagging every new product as `new-arrival` (via a Shopify Flow triggered on product creation), but rejected it: production gets periodic bulk uploads, and a bulk upload of older backlog titles would flood the New Arrivals rail for a week, indistinguishable from genuinely new stock.

**Instead: the client applies the `new-arrival` tag by hand**, only when a title is genuinely new stock on the shelf. A Shopify Flow still auto-*removes* the tag after 7 days, so nobody has to remember to clean it up.

**Follow-up to revisit later** (not committed to): if a better "genuinely new" signal ever becomes available — e.g. a dedicated "date received" field distinct from Shopify's product-created timestamp — this could go fully automatic. Flagged, not scheduled.

### Client steps: marking a title as a New Arrival

1. Open the product in Shopify Admin → Products.
2. In the **Tags** field, add: `new-arrival` (lowercase, with the hyphen, exactly as written).
3. Save. It appears in the New Arrivals section on the site right away.
4. You don't need to remove it — it automatically drops off after 7 days. To pull it sooner, just delete the `new-arrival` tag from the product.

Note: only works for rental movies (already tagged `Rental`, category Videos) — tagging a piece of merch `new-arrival` won't make it appear here.

### Setup status

- [x] Dev store: smart collection exists and rule set verified correct.
- [x] Dev store: 5 sample titles manually tagged so the rail shows real content (OPEN SEASON, Never Been Kissed, The Adventures of Pluto Nash, The Grifters, Who's the Man?).
- [ ] Dev store: build the auto-expiry Flow (Admin → Apps → Flow) — see steps below — so those demo tags actually age out, and so the mechanism is validated before copying to production.
- [ ] Production: run the same setup (below).

### Production setup steps

1. **Confirm tagging is in place.** This only works if production movie products already carry the `Rental` tag and the `Videos` category — should already be true from the normal upload/reformat pipeline (`data-cleanup/`), but worth a spot check first (this rail silently shows nothing if either is missing).
2. **Create the `New Arrivals` smart collection.** The script that created it on dev works unchanged against production (idempotent — safe to re-run):
   ```bash
   SHOPIFY_STORE=p0wkgv-wy.myshopify.com ./scripts/create-new-arrivals-collection.sh
   ```
   Or manually in Admin → Products → Collections → Create collection: title "New Arrivals", handle `new-arrivals`, match **all** conditions: Category = Videos, Tag = Rental, Tag = new-arrival. Sort: Newest to oldest.
3. **Build the auto-expiry Flow.** Admin → Apps → Flow → Create workflow:
   - **Trigger:** "Tag added"
   - **Condition:** tag equals `new-arrival`
   - **Action 1:** "Wait" → 7 days
   - **Action 2:** "Remove tags" → `new-arrival` → apply to the triggering product

   Name it "New Arrival tag auto-expiry" and turn it on.
4. No theme changes needed — the section already reads `collections['new-arrivals']` by handle.

---

## Community Picks (homepage "Community picks" section)

### How it works

Sourced from a `staff_pick` metaobject (Admin → Content → Staff picks — displays under the "Community Pick" name). Each entry has four fields:

| Field | Label in admin | Required? |
|---|---|---|
| `product` | Product | **Yes** — the pick doesn't render at all without one |
| `quote` | Quote | Optional, but it's the whole point of the section |
| `staff_name` | Community Name | Optional |
| `staff_link` | Community Link | Optional (e.g. a link to that person's Instagram) |

The section only counts an entry as "shown" once it has a resolved Product — an entry with everything else filled in but no product silently doesn't render, and the whole section falls back to "No picks yet" if zero entries qualify. **This is exactly what was happening before this pass** — all 8 existing entries had every field filled in except Product.

### What we fixed

Set the Product field on 5 of the 8 existing entries (and wrote real quotes/names for them, replacing placeholder text), so the section now shows real content:
- "007: Tomorrow Never Dies" — quote from "Jordan"
- "101 Dalmatians" — quote from "Sam"
- "12 Monkeys" — quote from "Priya"
- "13 Assassins" — quote from "Marcus"
- "10,000 BC" — quote from "Dana"

**3 entries are still incomplete** (no Product set, placeholder joke text) — either finish them (Admin → Content → Staff picks) or delete them:
- `this-is-a-movie-i-like-cause-it-reminds-me-of-the-time-i-was-locked-out-of-my-house`
- `a-new-one`
- `copy-of-i-really-love-this-movie-so-much-its-so-very-good-wow-i-do-love-it-1`

There's also 1 entry left in **Draft** status (`copy-of-i-really-love-this-movie-so-much-its-so-very-good-wow-i-do-love-it`) — draft entries never show regardless of their fields, so it can stay as a scratch draft or be deleted.

### Client steps: adding a Community Pick

1. Admin → Content → Staff picks (metaobject type: Community Pick) → Add entry.
2. **Product** — search and select the actual product. This is the one field that makes it show up at all.
3. **Quote** — a short one- or two-sentence blurb.
4. **Community Name** (optional) — who picked it.
5. **Community Link** (optional) — a link for that name (e.g. their Instagram), only shows if a name is also set.
6. Save and make sure the entry's status is **Active**, not Draft.
7. **Also add the `community-pick` tag to the product itself** (Admin → Products → that product → Tags field). This is a separate step from the metaobject entry above — it's what makes the "Community picks" filter toggle appear on the shop-all browsing page. Skipping this doesn't break the homepage section, but the filter toggle silently won't show up (confirmed on dev: it was broken until this tag was applied — Shopify's filter only appears once at least one product carries the tag).

To remove a pick from the homepage without deleting the record, either set it to Draft or clear the Product field. To remove it from the shop-all filter too, also remove the `community-pick` tag from the product.

### Production status

Not yet set up — the `staff_pick` metaobject definition and any entries need to exist on production before this section will show anything there. Out of scope for this pass; flag when production content work starts.

---

## Events (homepage "Events & screenings" + full `/pages/events` calendar)

### How it works

Sourced from an `event` metaobject (Admin → Content → Events). Both the homepage's 4-event preview and the full events-calendar page pull from the same metaobject list — the homepage just shows fewer.

| Field | Label in admin | Notes |
|---|---|---|
| `name` | name | |
| `date` | date | Only events **today or later** ever show — past events disappear automatically, no manual cleanup needed |
| `description` | description | Shown only on the full calendar page, not the homepage cards |
| `audience` | audience | Preset choices: Members / Public. **Display label only** — it does *not* restrict who can see the event. A "Members" event is still fully visible and clickable by anyone, just shows a "Members" badge. If you need an event to actually be hidden from non-members, that's not built — flag it if you need it. |
| `link` | link | Optional. If set, the event name becomes a clickable link (e.g. to an RSVP or ticket page). |

Events sort automatically, soonest first — no manual ordering.

### Client steps: adding an event

1. Admin → Content → Events → Add entry.
2. Fill in **name** and **date** (required for it to render sensibly).
3. **description** — only shows on the full `/pages/events` calendar, not the homepage.
4. **audience** — pick Members or Public. Remember: this is just a badge, not a visibility restriction.
5. **link** (optional) — add if there's somewhere to send people (RSVP, ticket page, Instagram post, etc.).
6. Save, status **Active**.

To take an event down early, either delete it or set its date in the past — either way it stops showing.

### Current dev-store content

3 test entries exist, all placeholder ("sample event 1/2/3") — 2 are already in the past and auto-filtered out; one ("sample event 1," dated 2026-08-31) is still upcoming and will show live until it's replaced or its date passes. Replace with real events before this is client-facing.

### Production status

Not yet set up — same as Community Picks, the `event` metaobject and entries need to exist on production. Out of scope for this pass.

---

## Header announcement bar

### How it works

This is Horizon's built-in announcement bar (not custom LMS code) — a single scrolling strip at the very top of every page, above the logo/nav. It's edited entirely in the **theme customizer**, not through Admin → Content.

**Currently**: one announcement block exists, but its text is blank. Blank text means that specific slide doesn't render — but the announcement bar's outer wrapper still renders regardless (with ~15px padding top and bottom), so **there is currently a blank empty strip at the top of every page**, not just an invisible/collapsed section. This is a real layout quirk worth fixing, not just a content gap — either add real text or remove the section/block entirely.

You can have **multiple** announcement blocks — if there's more than one, they auto-rotate on a timer (with left/right arrows shown), like a mini slideshow. With exactly one, it just sits there statically.

### Client steps: editing the announcement bar

1. Admin → Online Store → Themes → Customize (on the correct theme).
2. In the left sidebar, find **Header** → **Announcement bar**.
3. Click the announcement block under it (there's one now, named "Announcement").
4. Edit the **Text** field — this is what scrolls/displays. Supports basic rich text (bold, links via the text formatting toolbar).
5. Optional: **Link** — makes the whole bar clickable (e.g. link to a sale, an Instagram post, the membership page).
6. Optional styling: font, size, weight, letter spacing, case (upper/normal), text color — all in the same block settings panel.
7. To add a second rotating message: click "Add block" under Announcement bar, add another Announcement block, repeat steps 4–6. With 2+ blocks it'll auto-rotate; **Scroll speed** (in the parent Announcement bar section settings, not the block) controls how many seconds each one shows.
8. To remove the bar entirely (and fix the blank-strip issue if no real content exists yet): either delete the one block, or disable/remove the whole "Announcement bar" section from the Header group.

### Recommendation

Until there's a real message to put here (a promo, "Now open," a shipping note, etc.), either fill in real text or remove the section — don't leave it as an empty visible strip. Flag which you'd prefer.

### Production status

Same theme code will apply once pushed to production; the block's actual text/settings are theme-editor content, not code, so they'll need to be set independently on production's theme (they don't come along with a code push unless carried over via `config/settings_data.json`).
