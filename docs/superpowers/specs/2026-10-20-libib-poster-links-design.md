# Homepage links to Libib — design

**Date:** 2026-10-20 (revised 2026-10-21)
**Store:** production (`p0wkgv-wy.myshopify.com`, live theme `166751961338`) and the client's Libib account (`Rental Library`, `library_id` 2603141, published at `libib.com/u/littlemoviestore`)
**Builds on:**
- the daily tag job: `claudedocs/2026-10-20-libib-tags-job-overview.md` and `docs/superpowers/specs/2026-10-20-libib-tag-sync-design.md`
- the join_id research: `claudedocs/2026-10-13-libib-item-links-join-id.md`

## Intent

The public Libib page becomes where customers browse the rental library and check whether a copy is in. The Shopify homepage points there.

- The site-wide "Rental Library" links go to the Libib page.
- So do the New Arrivals rail's buttons.
- Each movie poster on the homepage opens that movie's own Libib item.

The Shopify-side collection pages will be hidden, which is separate work and not part of this design.

### How we got here (2026-10-20)

- **Libib collections were ruled out.** An item lives in exactly one collection, items that are checked out can't be moved, and moving an item changes its public link.
- **A pre-searched Libib link isn't possible.** The public page reads only `?id=` and `?solo=` from its URL, and its search runs only when someone types in the box and presses Enter (checked against `/js/u/search.js?v=65`).
- **This scope (user, 2026-10-21):** homepage only, with the "Rental Library" header and footer links and the New Arrivals buttons going to the Libib base page. No Shopify collection pages.

## Goals

1. **"Rental Library" in the header and footer, and the hero's "BROWSE THE LIBRARY" button,** link to `https://www.libib.com/u/littlemoviestore`.
2. **The New Arrivals rail's buttons go to the same Libib page.** These are "View all" and "+ N more" in `sections/lms-new-releases.liquid`.
3. **Each movie poster on the homepage opens that movie's Libib item**, at `https://www.libib.com/u/littlemoviestore?id=<join_id>`. Two sections have posters:
   - the New Arrivals rail (`sections/lms-new-releases.liquid`)
   - Community Picks (`sections/lms-staff-picks.liquid`)
4. **The daily job stores each homepage movie's Libib link.** `python3 -m catalog libib tags` already matches every `new-arrival` and `community-pick` product to its Libib item. It also looks up that item's `join_id` and writes it to a product metafield. Those two tags are exactly the products the homepage sections can show.

## Non-goals

- **Hiding the Shopify collection pages.** That's a separate change.
- **Links outside the homepage, header and footer.** Search results, the Shopify movie page and every other section keep their current links.
- **A `join_id` for every rental.** Backfilling all ~3,500 rentals is the larger plan in the join_id research doc. Only tagged products get one here.
- **Changing which products are new arrivals or community picks.** The tag rules are unchanged.
- **Showing each title once.** Rentals are still one product per copy, so a title with several copies could show several posters, each opening its own copy. *(My call: accept this.)*
  - On 2026-10-20 the `new-arrivals` collection held 50 products for 50 titles, so this doesn't happen today.
  - The planned move to one product per movie + format removes it.

## Anti-goals

- **A broken or wrong link on a poster.** A product with no `join_id` falls back as described under "Poster links".
- **Writing a `join_id` from an ambiguous lookup.** See "Lookup".
- **A barcode in a log, report or Actions output.** The repo and its Actions logs are public. The lookup sends the barcode to libib.com, and nowhere else.
- **Breaking the job's tag work.** A failed lookup is reported per product and never stops the tag changes.

## How it works

### Data

- **New product metafield `custom.libib_join_id`**, type `number_integer`, storefront `PUBLIC_READ`.
  - Create the definition once on production. The job's app already has `write_products`.
- **The value stays when a product loses its tag** *(my call)*. It's still correct, and the later backfill wants it.

### Lookup (in the daily job)

- **Endpoint:** the public published-site search, `POST https://www.libib.com/u/littlemoviestore/search` with `keywords=<copy barcode>&library_id=2603141&offset=0&limit=50`. Parse the unique `data-join-id` values in `item-info`.
- **No login, no browser.** It's plain HTTP, so it can run before the Playwright session.
- **Which products:** every product the job's final plan leaves tagged `new-arrival` or `community-pick` that has a matched Libib item, using that item's copy barcode. That's about 54 today.
- **Every run, throttled.** Look up all of them each day, not only missing ones, so moved or re-added items get their new link. Throttle the requests because the endpoint is undocumented.
- **Exactly one hit:** use it. *(Builder's call:)* also check that the hit's title matches the Libib export title.
- **Several hits:** keep any stored value, and report the product by title and Libib item id.
- **Zero hits with a value stored** *(my call)*: clear it, but only when the zero is definitive:
  - the request succeeded and parsed
  - at least one other lookup in the same run returned exactly one hit, which shows the endpoint works (the selftest also checks it separately)
  - no more than 10 products would be cleared in this run

  Otherwise keep every stored value and report it, so a broken endpoint can't wipe links in bulk.

### Writing

- **`metafieldsSet` (or a delete for clears)**, only where the value changes.
- **Same approval `Plan` as the tag changes.** The writes show in the dry run and the report. Like other Shopify writes, they don't count toward `max_changes`.
- **Report columns:** product title, Libib item id and `join_id`. No barcode.

### Theme (`theme/lms-redesign-v4/`)

#### Shared

- **One place builds the Libib URL.** For example, a `snippets/lms-libib-url.liquid` that takes an optional `join_id` and outputs the base URL, or `?id=<join_id>` when one is given. The card snippet and both sections use it, so the base URL lives in one spot.
- **Base URL** `https://www.libib.com/u/littlemoviestore`. *(Builder's call:)* hardcode it in that snippet, or make it a theme setting next to `lms_known_formats`.
- **Same tab** *(my call)*. Libib's "Website Link" brings customers back.

#### Poster links

- **`snippets/lms-product-card.liquid`:** add an optional `link_to_libib` parameter, default false, and document it in the comment block. When it's true, the `href` is the Libib item URL when `card_product.metafields.custom.libib_join_id` is set, and the Libib base URL when it isn't. Other pages that render the card don't pass the parameter, so they don't change.
- **`sections/lms-new-releases.liquid`:**
  - pass `link_to_libib: true` to the card
  - point "View all" and "+ N more" at the Libib base URL
  - update the header comment, which describes the old targets
- **`sections/lms-staff-picks.liquid`:** the poster `<a>` gets the same rule, using `pick_product.metafields.custom.libib_join_id`.

#### Rental Library links

- **Header:** "Rental Library" is an item in the `main-menu` menu, currently linking to `/collections/all-movies`. It's changed by hand in the admin (Content → Menus), not through the API: a menu update resubmits the whole menu, so a mistake can wipe it. This is a rollout step, not code.
- **Footer:** the link is inside a rich-text block in `sections/footer-group.json` (`<a href="/collections/all-movies">Rental Library</a>`).
  - It's merchant-editable, so pull it from production before editing.
  - Change only that `href`, then push it with `--only sections/footer-group.json`.
  - The client could also change it in the theme editor.

## Constraints

- **Production is the working store** (CLAUDE.md TEMPORARY block).
  - Run `shopify theme list` to confirm the live theme.
  - Pull before every push, and push narrowly with `--only`.
- **All production writes need approval:**
  - the metafield definition
  - the footer push and the theme push
  - the first job run with lookups, as a dry run reviewed with the user before `--approve`

  The menu edit is the user's or the client's to make in the admin.
- **Order matters.** Deploy the job change and let it fill `join_id`s before pushing the theme. Until then, posters use the fallback.
- **The `/search` endpoint is undocumented.**
  - Add a read-only check to `catalog/libib/selftest.py`: one known item's lookup must return exactly one `join_id`. Then a broken endpoint fails the daily run's selftest.
  - Stored links keep working if the lookup breaks. They use Libib's own "Copy Link" URL format.
- **Worktree:** `.worktrees/libib-poster-links`, on branch `feature/libib-poster-links`.
- **Tests:**
  - Keep `plan_tags` pure.
  - Test lookup parsing and write planning in `tests/catalog/`, injecting the lookup through `TagDeps`.
  - Run the suite: `python3 -m unittest discover -s tests/catalog -p "test_*.py"`.
  - Run `shopify theme check --path theme/lms-redesign-v4`.

## Decided (user, 2026-10-21)

- **Poster fallback when there's no `join_id`** (a Floor Sale Community Pick, or before the first run): the **Libib base page**. Every homepage poster goes to Libib, and none of them leads to a Shopify page.
- **The hero's "BROWSE THE LIBRARY" button** (`templates/index.json`, `button_secondary.link`) moves to the Libib base page too. `templates/index.json` is merchant-editable, so pull it from production before changing it, and push it with the footer.

## Left to the builder

- where the lookup sits in `tags_command.py` (after the plan is computed, before approval)
- how the selftest gets its known item
- the snippet structure
