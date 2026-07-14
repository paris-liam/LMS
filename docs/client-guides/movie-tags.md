# Movie tag vocabulary (canonical)

Genre, label/distributor, and curation are modelled as **product tags** (not metafields),
so there is no dropdown to enforce spelling. This file is the source of truth — tag
exactly as written here. Adding a value = add it here first, then use it.

## Genre — `genre-…` (a movie may carry several)

| Tag | Genre |
|---|---|
| `genre-action` | Action |
| `genre-adventure` | Adventure |
| `genre-animation` | Animation |
| `genre-comedy` | Comedy |
| `genre-crime` | Crime |
| `genre-cult` | Cult |
| `genre-documentary` | Documentary |
| `genre-drama` | Drama |
| `genre-fantasy` | Fantasy |
| `genre-horror` | Horror |
| `genre-musical` | Musical |
| `genre-mystery` | Mystery |
| `genre-noir` | Noir |
| `genre-romance` | Romance |
| `genre-sci-fi` | Sci-Fi |
| `genre-thriller` | Thriller |
| `genre-war` | War |
| `genre-western` | Western |

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

- Lowercase, hyphenated, ASCII. `Sci-Fi` → `genre-sci-fi`; `Kino Lorber` → `label-kino-lorber`.
- Genre/label are still filterable on the storefront, but note: Search & Discovery's
  native **Product tags** filter lists *all* tags in one combined facet — it does not
  split `genre-*` and `label-*` into separate named filters. Separate named Genre/Label
  facets would require custom theme prefix-grouping or reverting those two to metafields.
