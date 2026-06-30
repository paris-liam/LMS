# LMS × Supercycle — Storefront Feature Requests & Implementation Plan

A running record of the features being scoped for the Little Movie Store build (online **and** in-store), and how each one will be accomplished on Supercycle + Shopify (Horizon theme). Each entry notes whether it's native, configured, or a custom build, plus any caveats and open questions.

Features 1–8 were scoped from direct requests; Features 9–16 and the refinements were surfaced by reviewing the March 2026 investor deck against the plan.

**Scope key:** 🟢 Launch (June 5 grand opening) · 🟡 Phase 2 (post-launch) · ⚪ Future ("DVD Extras" / later)

_Last updated: 30 Jun 2026_

---

## ▶ Pre-Supercycle build track (START HERE)

Currently blocked on the client purchasing + installing Supercycle. This section is what to build **now** against the Horizon theme so that go-live is a *swap*, not a rebuild. Most of the list doesn't need Supercycle to exist yet.

### The principle

Wherever Supercycle plugs in, build a **clearly-bounded slot fed by stand-in data**. Three stand-ins unlock almost everything:

1. **Reserved PDP region for the Methods block** — leave a clearly-marked, empty container where the Methods app block will mount. Do **not** build a competing add-to-cart; Supercycle takes over the theme's existing one.
2. **Manual `Has active subscription` customer tag** on a test customer — this is the literal tag Supercycle applies to active members, so applying it by hand makes all member-gating and discount logic real and testable now.
3. **`custom.*` stand-in metafields** for availability/method values — build and test facets and `data-`attribute rendering against these, then repoint the keys to `supercycle.*` at install.

> ⚠️ **Never hand-create the `supercycle` metafield namespace.** It's app-reserved and will collide when the app installs. Use `custom.*` for stand-ins and swap later.

### Buildability index

Legend: 🔨 build now (no Supercycle dependency) · 🧩 build now with a stand-in (swap later) · 🔒 blocked until installed

| # | Feature | Scope | Buildability | Blocked part (until install) |
|---|---|---|---|---|
| — | **Theme foundation** (not a numbered feature) | 🟢 | 🔨 | none — fully buildable, critical path |
| 1 | Availability filter | 🟢 | 🧩 | real availability values + Supercycle Methods filter block |
| 2 | Back-in-stock notify | 🟡 | 🧩 | the Return-trigger automation |
| 3 | Catalogue / PDP | 🟢 | 🔨 | only the Methods-block slot (reserve it) |
| 4 | Curation tags | 🟢 | 🔨 | none |
| 5 | Purchase actions (membership/rental) | 🟢 | 🔒 | plan/calendar config + Membership/Methods blocks (page *layout* + gift-card product buildable) |
| 6 | Member discounts & event gating | 🟢 | 🧩 | nothing structural — uses the stand-in tag |
| 7 | Buy / ship / intake | 🟢 | 🔒 | resale+rental config, create-item, shipping buffers (retail catalogue + intake form buildable) |
| 8 | Mystery packs / birthday movie | 🟢 | 🧩 | mystery-pack inventory reconciliation (8a product + 8b birthday buildable) |
| 9 | In-store / POS | 🟢 | 🧩 | rental-at-POS + serial scanning (retail POS buildable) |
| 10 | Movie player rentals | 🟡 | 🔒 | calendar method + deposits |
| 11 | Space rental | ⚪ | 🔨 | none (booking app, no Supercycle dependency) |
| 12 | Ticketed events | 🟡 | 🔨 | none (gating uses stand-in tag) |
| 13 | Weekly drops | 🟢 | 🔨 | none |
| 14 | Retail bundles / kits | 🟢 | 🔨 | none |
| 15 | "If you liked…" recs | 🟢 | 🔨 | none |
| 16 | Loyalty / punch card | 🟡 | 🔨 | none (no Supercycle dependency) |

### Suggested build order (everything below needs no Supercycle)

1. **Theme foundation** — Horizon customization, design system, IA/nav, homepage, brand identity, and content/marketing pages (About, community + membership *pitch* pages, events page shell, cart/checkout styling). The design-forward core; on the critical path regardless.
2. **Catalogue + PDP (F3)** — browse experience and product page, with a reserved Methods-block slot on the PDP.
3. **Shopify data structure** — collection taxonomy, product **metafield definitions** (format, label, new/used, curation), and the **non-serialized retail catalogue** (apparel, snacks, art, merch — never touches Supercycle).
4. **Curation & merchandising** — F4 tags/collections/badges, F13 weekly drops + "New this week", F14 retail bundles, F15 recommendation rails.
5. **Facets (F1)** — format/label/new-vs-used facets + Search & Discovery scaffolding, wired to `custom.*` stand-in metafields for availability.
6. **Member-gated logic** — F6 segment + 10% automatic discount + event gating, and F8b birthday gating, all against the manual `Has active subscription` tag.
7. **Capture UIs** — F2 notify-me form, F8b birthday-capture field + reward mechanism, F5a membership page layout, F8a mystery-pack product, F5b gift-card product.
8. **POS + apps** — F9 Shopify POS for plain retail; evaluate booking (F11), events/ticketing (F12), and loyalty (F16) apps.

### Hand-off note for Claude Code

- The three stand-ins above are the integration contract. Keep them isolated so swap-day is wiring, not construction.
- The PDP must leave an empty, labelled container for the Methods block and must not implement its own rental/buy add-to-cart.
- Do not create anything under the `supercycle` metafield namespace; use `custom.*`.
- Member-gating reads the `Has active subscription` customer tag (and later `customer.metafields.supercycle.membership`); build against the tag now.

---

## Reference: how Supercycle exposes front-end functionality

Four integration tiers, lowest-effort to most custom:

1. **App embed ("Supercycle Engine")** — global embed enabled in the theme editor; holds date-format, app-block style, and customer-portal style settings. Nothing renders without it.
2. **App blocks (no-code)** — OS 2.0 theme-editor blocks: **Methods** (PDP, takes over the theme's add-to-cart), **Membership plans** (required enrollment path), **Availability / Methods filter** (collection pages).
3. **Liquid + metafields** — namespaced `supercycle.*` metafields on products, variants, and customers for conditional rendering and merchandising. Set by Supercycle; not edited manually.
4. **Storefront API** — for fully custom frontends/bundles. Currently under development and gated to select merchants by request — not safe to architect around yet.

---

## Feature 1 — Filter catalogue by availability (storefront) · 🟢 Launch · 🧩 Build now (stand-in)

**What I'm asking for:** Let customers filter/browse the catalogue by whether a title is currently available, ideally with date-aware (calendar) availability later.

**Data source:** Supercycle writes availability into variant metafields:
- `supercycle.uncommitted_inventory` (boolean) — intended for collection inventory filtering
- `supercycle.uncommitted_inventory_count` (integer) — available-now count (visible, not retired, not committed to an active rental)
- `supercycle.future_availability_inventory` (boolean) — supports calendar-based availability filtering

**How we'll accomplish it — three options:**

| Option | Approach | Effort | Notes |
|---|---|---|---|
| A. Smart collection | Use `supercycle.uncommitted_inventory` as a condition in an automatic collection → "Available now" collection | Low | Server-side, no JS. Cleanest "available now" path. |
| B. Built-in availability facet | Supercycle's **Methods filter** app block via Shopify Search & Discovery: define `supercycle.methods` metafield with filtering on, add "Rental availability" + "Supercycle Methods" filters, copy the collection section ID, add the Methods filter block, hide the default Search & Discovery filters with CSS | Medium | The "official" customer-facing filter. **Currently in beta — known bugs/limitations.** Validate stability before launch. |
| C. Custom client-side JS | Render the variant metafields into `data-` attributes on each card and filter/hide in JS | Medium | Good for "available now." Date-aware filtering needs the availability-timeline endpoints (gated Storefront API) — not pure client-side yet. |

**Caveat:** Theme product grids render server-side, so JS-only filtering only sees products already in the DOM (pagination concern). At LMS scale (~few hundred titles, ~2 copies each), rendering the full collection or using the Search & Discovery facet avoids this.

**Recommendation:** Start with Option A (smart collection) or Option B (Search & Discovery facet). Reserve Option C for polish once core flows work.

**Deck refinement — more than availability.** The deck implies browsing by **format** (4K / Blu-ray / VHS / DVD), **label** (Criterion / A24 / Arrow / Kino Lorber), and **new vs. used**. These are ordinary Shopify product attributes (tags or metafields) surfaced as Search & Discovery facets — define them in the *same* filter set as availability and the Feature 4 curation tags rather than piecemeal.

**Open questions:** Is the beta availability filter (Option B) stable enough to depend on at launch?

---

## Feature 2 — Back-in-stock / "notify me when returned" email · 🟡 Phase 2 · 🧩 Partial (capture now)

**What I'm asking for:** Customer receives an email when a title they want is returned / back in stock.

**Native status:** No native customer-facing waitlist ("notify me when available" signup). The native building block is **Shopify Flow**: Supercycle exposes **Return created** and **Return updated** triggers, and Flow can send email off those triggers. So the *event* (item returned) is fully automatable.

**The gap:** Flow's return trigger knows an item came back but not *which customers were waiting* for it. There's no built-in waitlist matching.

**How we'll accomplish it — two options:**

| Option | Approach | Effort | Notes |
|---|---|---|---|
| A. Custom waitlist | Capture interested customers per product (customer tag, metaobject, or list). On **Return created**, loop `returnOrder.rentals` and email anyone waiting on that product/variant | High | Full control, no dependency on inventory writeback behavior. The reliable path. |
| B. Third-party back-in-stock app | Klaviyo / dedicated back-in-stock app watching Shopify's native inventory quantity (0 → 1) | Low–Medium | **Only works if Supercycle returns restore Shopify's native inventory level.** Unverified. |

**To confirm with Supercycle (blocking for Option B):** Do returns write back to Shopify's native tracked inventory quantity, or only flip Supercycle's own committed/uncommitted state? This determines whether any off-the-shelf back-in-stock app will fire at all.

---

## Feature 3 — Show the inventory / catalogue list · 🟢 Launch · 🔨 Build now

**What I'm asking for:** Display my inventory list "in the app" — let customers browse the catalogue of titles.

**Key distinction in Supercycle — inventory exists at two levels:**
- **Products = the titles** (e.g., a given film). Standard Shopify products; this is what customers browse. Each must be imported into Supercycle (so methods + availability data exist) and have the Methods block on its PDP.
- **Items = serialized copies** (`LMS-NNNNNNN`). Admin-side only. Customers never see individual serials — only the product and its available count.

**How we'll accomplish it:**

Customer-facing catalogue (browse the titles):
- Standard Shopify **collections** rendered by Horizon's collection template (product grid). No Supercycle-specific display component needed.
- Combine with the availability metafields (Feature 1) to show/sort/filter by what's available.
- Each card links to the PDP, where the Methods block handles rent/buy.

Merchant / internal inventory (the serialized copies):
- Managed in Supercycle's **Items** view in the Shopify admin (condition, location, timeline per serial).
- For a custom internal inventory screen later, the **Admin API → List all items** endpoint exposes serials, condition, location, and availability programmatically.

**Caveat:** Don't surface individual serials to customers — the customer-facing unit is the product/variant + availability count, not the `LMS-NNNNNNN` serial.

---

## Feature 4 — Product tags for curation & filtering ("Rare Finds", "Staff Picks") · 🟢 Launch · 🔨 Build now

**What I'm asking for:** Tag products so I can group, filter, or feature them (e.g., "Rare Finds", "Staff Picks").

**This is standard Shopify** — independent of Supercycle. (Supercycle uses *customer* tags for membership and `supercycle.*` *metafields* for its own product data; curation tags are separate and safe to use freely.)

**How we'll accomplish it — pick a labeling mechanism, then a surface:**

Labeling:
- **Shopify product tags** (e.g., `staff-picks`, `rare-finds`) — quickest; good for collections and filters.
- **Product metafields** (e.g., a boolean "Staff pick", or a single-select) — tidier for typed values and cleaner Search & Discovery filtering; avoids tag sprawl. Use if curation grows structured.

Surfaces (any combination):

| Surface | Mechanism |
|---|---|
| Dedicated page/section (e.g., a "Staff Picks" collection) | Automated collection (tag = `staff-picks`) or hand-picked manual collection |
| Storefront filter on collection pages | Enable the tag/metafield as a **Search & Discovery** filter — sits alongside the availability/method filter from Feature 1 |
| Badge on cards/PDP | Liquid: `{% if product.tags contains 'staff-picks' %}…badge…{% endif %}` |

**Plan-together note:** If these should be storefront filters next to the availability facet, they all run through Search & Discovery — so define the full filter set together rather than piecemeal.

**Decision to make:** tags vs metafields for curation (simplicity vs. cleaner filtering/typing).

---

## Feature 5 — Purchase actions: buy membership, gift membership, single rental · 🟢 Launch · 🔒 Mostly blocked

**What I'm asking for:** Set up the three buying actions — buy a membership, gift a membership, and do a single non-membership rental.

### 5a. Buy a membership — native, fully supported

| Step | Where | Detail |
|---|---|---|
| Create the plan | Supercycle admin → Settings → Methods → Membership → Add plan | Set billing interval + price (LMS = single yearly purchase option), credit allowance (items held at once), swap allowance (order/return cadence). Saving creates a linked Shopify **plan product** (placeholder — never sell directly). |
| Enable on products | Supercycle → Products | Turn on membership method per title; set each title's credit cost. |
| Build membership page | Shopify admin + theme editor | Create a "Membership plans" collection, add plan product(s); create a page; add the **Membership plans app block** pointed at that collection. |

**Buy action:** add-to-cart inside the Membership plans block → checkout → Supercycle activates membership and assigns credits. This block is the **only** valid enrollment path.

**Caveat:** Shopify can't hide a plan product from the "all" collection while keeping it in the membership collection. Filter plan products out of collection pages in Horizon, or set them to unlisted.

### 5b. Gift a membership — NOT native, needs a workaround

**Why it's awkward:** enrollment binds the membership + credits to the *purchasing customer's account*, and billing runs on a recurring Shopify selling plan. A straight "buy for someone else" activates it on the buyer. The Admin API also has **no "create/assign membership to a customer" endpoint**, so custom redemption isn't clean either.

| Option | Approach | Notes |
|---|---|---|
| A. Shopify gift card (recommended) | Sell a gift card for the membership amount; the **recipient** applies it when they self-enroll through the membership block on their own account | Activation stays correct. For the yearly tier, covers year one; renewal needs the recipient's own card on file. |
| B. Concierge / manual | Sell a plain "gift membership" product (normal Shopify product, not a plan product); coordinate enrollment with the recipient manually | Operationally heavy, doesn't scale. |
| C. Ask Supercycle | They do custom work over Slack — ask if there's a supported gifting pattern or a way to assign a membership to a specified account | See running questions. Also confirm with client whether gifting is needed at launch. |

### 5c. Single non-membership rental — native (Calendar method)

| Step | Where | Detail |
|---|---|---|
| Enable calendar method | Supercycle → Products → select title → Calendar | Add rental periods + pricing (≤4 periods recommended for UX), optional fixed fees / multi-market pricing. Turn on + save. |
| Storefront | Methods app block on the PDP | Renders the calendar option with a date picker; non-members select dates and use the taken-over add-to-cart. No membership required — calendar and membership coexist on the same PDP. |

---

## Feature 6 — Membership discounts & member-exclusive events · 🟢 Launch · 🧩 Build now (stand-in tag)

**What I'm asking for:** Apply membership discounts to purchases, and gate member-exclusive events.

**Shared hook — the membership signal.** Supercycle auto-applies customer tags reflecting subscription status: `Has active subscription`, `Has paused subscription`, `Has canceled subscription`, plus a `{Plan name} subscriber` tag. It also applies a separate `Supercycle member` tag.

> ⚠️ **Trap:** `Supercycle member` is applied to *anyone who has made a rental order* — including non-member one-off renters. Do **not** gate perks on it. Use **`Has active subscription`** (optionally + the plan-specific tag) as the active-member signal. When a membership lapses, the tag flips to `canceled`, so access/discounts fall away automatically.
>
> In Liquid, `customer.metafields.supercycle.membership` is the alternative signal.

### 6a. Membership discounts on purchases

| Step | Detail |
|---|---|
| Build a customer segment | Shopify segment from the `Has active subscription` tag |
| Create an automatic discount | Shopify **automatic discount** targeting that segment — applies at checkout, no code to enter |
| Scope | Works cleanly on **retail / resale** (normal Shopify line items) |

**Caveat (rentals) — now load-bearing.** The deck specifies the member perk as **10% off ALL purchases**. That makes whether a Shopify automatic discount applies to Supercycle's **calendar-rental and resale line items** a launch question, not a minor one — rental pricing comes from Supercycle method options + selling plans, so it may not stack. Retail/resale lines are normal Shopify and should be fine; rental is the uncertain one. Confirm with Supercycle (running question #4) before promising "10% off everything."

### 6b. Member-exclusive events

Not a Supercycle feature — Shopify storefront gating off the membership tag / metafield.

| Option | Approach | Notes |
|---|---|---|
| A. Theme Liquid gating | Events page/section checks membership and renders event + RSVP/ticket button for members, "members only" prompt otherwise (`{% if customer.tags contains 'Has active subscription' %}`) | Free, full control, no dependency. The design-engineer path. |
| B. Locked-content app (e.g. Locksmith) | No-code gating of pages/products by customer tag | Faster, adds an app. |

**Paid tickets:** model tickets as Shopify products, gate them the same way, optional member-only pricing via the 6a segment discount.

**Enforcement note:** Shopify can't hide a product by customer tag natively, so Liquid gating is *soft* — a non-member could hit the product URL directly. For genuinely members-only tickets, use a locking app that blocks the purchase; otherwise accept soft-gating for low-stakes events.

---

## Feature 7 — Buying products, shipping, and intake of used DVDs · 🟢 Launch · 🔒 Mostly blocked

**What I'm asking for:** Set up buying products (vs. renting), shipping them, and selling/donating used DVDs into inventory.

### 7a. Buy products outright — Resale method

Selling a disc from the catalogue = Supercycle's **Resale** method (not plain retail).

| Aspect | Detail |
|---|---|
| What it is | Sells individual **serialized items** (used/refurbished or end-of-rental-life). Permanently transfers ownership — unlike rental, the item does not return. |
| Pricing | Condition-based pricing (different prices per condition) → plugs into A/B/C grading. |
| Setup | Import product → enable Resale method → configure condition pricing. Items must exist in `Active` status. |
| Storefront | Resale shows as a method in the Methods block alongside rent; customer chooses buy vs. rent on the same PDP. |

**Inventory consequence:** a sold item moves to `Sold` and leaves the rental pool. At ~2 copies/title, selling a copy reduces borrow availability — ties into allowance rules.

**Note — two parallel catalogues.** The deck's product mix is broader than the serialized disc library. Serialized used media (VHS/DVD/Blu-ray) flows through Supercycle (resale + rental). But **new sealed media, apparel, gifts, art, snacks, media players, movie books, and vintage clothing are plain Shopify products that never touch Supercycle.** Keep the two clearly separated: Supercycle methods only attach to serialized stock.

### 7b. Shipping

Standard Shopify — shipping profiles, rates, fulfillment cover both resale and rental dispatch (Supercycle rides on Shopify checkout). Rentals add logistics buffers (prep/delivery/return/restock) + return logistics, but shipping mechanics are Shopify's. In-store pickup already enabled → shipping is the complement (customer picks pickup or ship at checkout).

**Gotchas to pre-empt:**
- **Split shipping:** carts mixing items with different fulfillment timing / shipping profiles / locations get split → multiple shipping charges. Fix: turn off Split shipping in Shopify (one label, one charge). Likely here (rental + resale + pickup in one cart).
- **"Ships {date}" label:** Shopify reads the fulfillment date from Supercycle's selling plan and shows a "Pre order ships date" that can display a wrong/alarming future date on rentals. Fix: edit that theme content label to neutral text (e.g. "Ships soon") or clear it.

### 7c. Selling / donating used DVDs into inventory (intake)

Splits in two — only the second half is Supercycle.

**Inventory creation (IS Supercycle):** once received and graded, create a serialized **item** against the matching product — set serial (`LMS-NNNNNNN`), condition, location, status `Active`, and enabled methods (rent/resale). Via Inventory area, Scanner app, or Admin API create-item endpoint (bulk). If the title isn't in the catalogue, create the Shopify product → import → add item. Consignment is supported (attribute revenue to a consignor) if sellers get a share.

**Customer-facing intake (NOT a Supercycle feature):** trade-in is referenced as a *source* of resale inventory and is in the marketing, but there's no documented turnkey "sell us your DVD" storefront flow with valuation/payout. Build as a process:

| Step | Approach |
|---|---|
| Intake form | Shopify page + form (Shopify Forms, a form app, or custom). Boutique scale: in-store / email may suffice. |
| Appraisal | Manual grading + offer. |
| Payout | **Donation:** the deck rewards donors with **free rentals** (not just thanks) — issue rental credit or a free-rental code, which ties into the membership credit system rather than a gift card. **Buying/trade-in:** no Supercycle payout mechanism; use **Shopify gift card / store credit** (keeps value in-store) or cash/manual. |
| Add to inventory | Grade → create the serialized item (Supercycle step above). |

---

## Feature 8 — Mystery packs & member birthday movie · 🟢 Launch · 🧩 Partial

**What I'm asking for:** A "mystery pack" product (buy it, store fills it with random discs and sells it), and a free kept movie on a member's birthday.

> Note: Supercycle **bundles** don't fit either — they group *known* component products into a *rentable* unit and need Storefront API work. Both features below live outside Supercycle's methods.

### 8a. Mystery packs

Split the sale from the inventory.

| Layer | Approach |
|---|---|
| The sale | Plain **Shopify product** ("Mystery 3-Pack", flat price, standard checkout). No Supercycle method — customer buys a generic SKU, not a chosen serialized item (which is why Resale doesn't fit). |
| The inventory | **Manual reconciliation**: on fulfillment, mark each disc placed in the pack as `Sold`/`Retired` in Supercycle so it leaves the availability pool. Skipping this leaves them showing as borrowable. |

**Recommendations:**
- Draw pack discs from a **dedicated surplus / C-grade / duplicate pool**, not rental-pool copies — otherwise each pack eats borrow availability at ~2 copies/title.
- **Cap the mystery-pack product's Shopify inventory** to the surplus count to avoid overselling.
- Optional: Shopify Flow on "order contains mystery pack" → reconcile-inventory task (disc-picking stays human).

**Client decision:** which disc pool feeds mystery packs (surplus/C-grade vs. rental pool).

### 8b. Free birthday movie for members

Supercycle's only role is the member signal (`Has active subscription` tag, Feature 6). Three Shopify/app pieces:

1. **Capture birthdays** — not native to Shopify customer accounts. Add a birthday field at membership signup (or post-enrollment profile) → store as a **customer metafield**. Prerequisite; small build.
2. **Trigger on the day** — email platform birthday flow (e.g. Klaviyo), a birthday-reward app, or a daily scheduled Shopify Flow that finds active members with a birthday today. Gate on the member segment.
3. **Deliver the free kept movie** — either a **100%-off single-item discount code** (unique, single-use, scoped to an eligible collection or value cap), or a **gift card / store credit** worth ~one disc's value.

**Client decision (important):** scope the reward (eligible "birthday picks" collection or max value). An uncapped "free movie" is an open liability against rare finds.

---

## Feature 9 — In-store / POS layer 🟢 Launch · 🧩 Partial (retail POS now)

**What it is:** LMS is primarily a physical store; the timeline lists "POS Set Up" explicitly. Every in-person action — retail sales, rental checkout, resale, intake, applying the 10% member discount, pickups/returns — happens at the counter through **Shopify POS** + Supercycle's POS support. The plan was online-only until now; this is the biggest gap.

| In-store action | Mechanism |
|---|---|
| Retail / resale sale | Shopify POS (serialized resale items + plain retail products) |
| Rental checkout & return | Supercycle at the counter — requires confirming POS coverage for rental, returns, and serial scanning (Scanner app) |
| Member discount in person | Member looked up at POS → `Has active subscription` segment applies the 10% |
| Pickup / drop-off | Counter fulfillment of online pickup orders + return intake |

**To confirm with Supercycle:** depth of POS support for rental checkout/return and counter-side serial scanning (running question #6).

---

## Feature 10 — Movie player (hardware) rentals 🟡 Phase 2 · 🔒 Blocked

**What it is:** Renting out media players (deck: "Movie Player Rentals"). A non-disc rental — a serialized player on the **Calendar method**, deposit-backed.

Fits Supercycle, but it's a different product type from discs: higher deposits, longer/different rental periods, more rigorous condition checks on return. Use Supercycle's deposit / risk features (card-on-file or deposit) for these specifically. Model each player as its own serialized item.

---

## Feature 11 — Space rental ⚪ Future · 🔨 Build now (no SC dep)

**What it is:** Renting the lounge/space for events or private use (deck: "Space Rental").

This is a **time-slot reservation of a resource**, not a product sale — it sits outside Supercycle's item model entirely. Needs a **booking / appointment app** (e.g. Sesami, Tipo) or an external booking tool, with member pricing applied via the Feature 6 segment if desired.

---

## Feature 12 — Ticketed / specialty events 🟡 Phase 2 · 🔨 Build now

**What it is:** "Specialty Events" + "Invites to members events" (deck pages 8, 16).

- **Member invites / RSVP** → already covered by Feature 6b gating (member tag).
- **Public or paid events** → need RSVP/ticketing: an events app, or model tickets as Shopify products (gate or member-price with the Feature 6 segment). Capacity/check-in handled by the app.

---

## Feature 13 — Weekly drops 🟢 Launch / 🟡 ramp · 🔨 Build now

**What it is:** Recurring timed releases of curated stock (deck: "Weekly drops").

A merchandising rhythm, not a one-off feature. Use **Shopify scheduled publishing** (timed collection/product go-live) or a dedicated drops app, paired with email + social. Pair the drop with a "New this week" collection and the Feature 1 facets. Mostly process + content cadence.

---

## Feature 14 — Curated retail bundles / "movie night kits" 🟢 Launch · 🔨 Build now

**What it is:** Fixed-contents bundles sold as one unit — e.g. a film + snacks "movie night kit" (deck pages 24–25). Distinct from **Supercycle rental bundles** (rentable, Storefront-API) *and* from **mystery packs** (random contents). This is a known-contents *retail* bundle.

Use **Shopify native bundles** (Shopify Bundles app) or a bundle app. If a bundle includes a serialized resale disc, the same reconcile-the-serial discipline from Feature 8a applies on fulfillment.

---

## Feature 15 — "If you liked…" recommendations 🟢 Launch · 🔨 Build now

**What it is:** Discovery surfaces — "If you liked…" / "Staff picks" recommendation rails (deck page 34). Given the brand thesis is *"discovery is broken; we're the curated middle,"* this is closer to core than nice-to-have.

- **Automated:** Shopify product recommendations (related / complementary products) on PDP and cart.
- **Hand-curated:** a product metafield of references ("if you liked → these") rendered as a rail in Horizon — fits the curated, design-forward positioning better than algorithmic-only.

---

## Feature 16 — Membership punch card / loyalty 🟡 Phase 2 · 🔨 Build now (no SC dep)

**What it is:** A punch-card / loyalty mechanic (deck page 34) separate from the $100/year membership.

Options: a **loyalty app** (Smile, Rivo, etc.), or build creatively on Supercycle **credits**. First decision is conceptual: is this its own points/punch program, or just a facet of membership? Resolve that before picking tooling.

---

## Future expansion ⚪ ("DVD Extras" — later phases)

Explicitly future in the deck; noted so they're not forgotten, not scoped now:

- **Drop-off return network** (partner cafés/shops accept returns) → maps to Supercycle **Locations** config + return logistics. Placeholder.
- **Mobile movie truck** → a pop-up of the same stack (Shopify POS mobile + Supercycle).
- **Local partnerships / second location** → out of software scope; the online store is being used to identify the second-location market.

---

## Stack beyond Supercycle (what actually runs each layer)

A useful reframe from the deck review: the real build is **Supercycle + Shopify + a few supporting apps**, not Supercycle alone.

| Layer | Runs on |
|---|---|
| Rental (calendar), membership, resale, serialized inventory, deposits | **Supercycle** |
| Retail products, collections, discounts, gift cards, segments, shipping, **POS**, scheduled publishing | **Shopify core** |
| Methods/Membership/filter blocks, Liquid member-gating, badges, recommendation rails, custom facets | **Horizon theme** |
| Filtering (Search & Discovery), space booking, event ticketing, loyalty, retail bundles, email (birthday / back-in-stock / drops) | **Supporting apps** (Search & Discovery, a booking app, an events app, a loyalty app, a bundle app, Klaviyo) |

---

## Running list — questions to confirm with Supercycle

1. Do returns write back to Shopify's **native inventory levels**, or only Supercycle's committed/uncommitted state? (Blocks Feature 2, Option B.)
2. Is the **availability filter app block** (Feature 1, Option B) stable enough for launch, given its beta status?
3. Is there any supported pattern for **gifting a membership** — e.g. assigning a membership to a specified customer account, or a redemption flow? (Blocks Feature 5b; also a client decision on whether gifting is needed at launch.)
4. Do **Shopify automatic discounts apply to calendar-rental and resale line items**, or only retail? **Launch-critical** — the deck promises members "10% off ALL purchases." (Affects Feature 6a.)
5. Is there a **trade-in intake module** or recommended pattern (customer-facing valuation/payout), or is intake entirely a custom build feeding the create-item flow? (Affects Feature 7c.)
6. How deep is **Supercycle's Shopify POS support** — does it cover in-person rental checkout, returns, and counter-side serial scanning (Scanner app)? Does the member discount apply correctly in POS? (Blocks Feature 9.)

_(Append new questions here as features are scoped.)_
