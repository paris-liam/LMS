# Movie tag vocabulary (canonical)

Label/distributor and curation are modelled as **product tags** (not metafields),
so there is no dropdown to enforce spelling. This file is the source of truth — tag
exactly as written here. Adding a value = add it here first, then use it.

> **Genre is NOT here** — it's the `custom.genres` metafield (a dropdown). Add new
> genres via **Settings → Custom data → Products → Genres → Edit choices**.

## Label / Distributor — `label-…` (one per movie)

| Tag | Label |
|---|---|
| `label-criterion` | Criterion |
| `label-a24` | A24 |
| `label-arrow` | Arrow |
| `label-kino-lorber` | Kino Lorber |
| `label-second-sight` | Second Sight |
| `label-vinegar-syndrome` | Vinegar Syndrome |
| `label-other` | Other / unlisted |

## Curation (bare tags)

| Tag | Effect |
|---|---|
| `staff-pick` | Files under **Staff Picks** (pair with a Staff pick note metafield). |
| `rare` | Files under **Rare Finds**; shows a "Rare" badge on the card. |
| `holiday` | Files under **Holiday Movies**. |

## Convention

- Lowercase, hyphenated, ASCII. `Kino Lorber` → `label-kino-lorber`.
- Label tags surface on the storefront via Search & Discovery's native **Product tags**
  filter, which lists *all* tags in one combined facet (label plus curation tags together).
  A separate named "Label" facet would require custom theme prefix-grouping or moving
  label to a metafield. Genre, by contrast, is a metafield and gets its own clean facet.
