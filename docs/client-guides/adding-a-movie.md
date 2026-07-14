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
| Country | Country of origin. For a co-production, enter the primary country (one value for now). |
| Runtime (min) | Runtime in minutes (number). |
| Genres | Tick every genre that applies (dropdown). |
| Format | Pick one: Blu-ray / DVD / 4K UHD / VHS. |
| Media condition | **Only for brand-new sealed stock you sell outright.** Leave blank for rental/resale copies — their condition is tracked per copy in Supercycle. |
| Staff pick note | The shelf blurb. Also add the `staff-pick` tag (below) so it shows in Staff Picks. |

## Tags (Tags box)
Label/distributor and curation live here as tags. **Type them exactly** — a typo makes a new, broken bucket. (Genre is the dropdown field above, not a tag.)

**Label / Distributor** — add one `label-…` tag:
`label-criterion` `label-a24` `label-arrow` `label-kino-lorber` `label-second-sight` `label-vinegar-syndrome` `label-other`

**Curation:**
- `staff-pick` → files it under **Staff Picks** (pair with a Staff pick note).
- `rare` → files it under **Rare Finds** and shows a "Rare" badge.
- `holiday` → files it under **Holiday Movies**.

## Adding a new genre or label
- **New genre:** an admin adds it once in **Settings → Custom data → Products → Genres → Edit choices**. It then appears for every product and as a storefront filter.
- **New label:** labels are just tags — type the new `label-…` tag on a product, keeping spelling consistent. The canonical label list lives in `docs/client-guides/movie-tags.md`; keep it in sync.

## What NOT to touch
Anything under a **Supercycle** heading (rental/resale/membership, per-copy
condition, serials, availability) is managed by Supercycle — don't edit it here.
