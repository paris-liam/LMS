# Two-copy products needing manual review

Source: `catalogue-batches/issues-combined.csv`, the "product has 2 variants" group (14 rows / 7 products).

Each of these has two rows sharing one Handle in the original export, with different `Option2 Value` — the tooling only supports one variant per handle, so these fail normalization. Only one row of each pair carries `Tags` (genre + Rental/Floor Sale); the other is blank, so splitting by handle alone isn't enough — the missing row's type/genre/price needs a decision, not a copy-paste.

| Handle | Row 1 | Row 2 | Note |
|---|---|---|---|
| `royal-tenenbaums` | `Standard` / `002A` / barcode `191-DVDROY-002A` / $0.00 / Tags: `Comedy, Rental` | `Standard` / `001A` / barcode `191-DVDROY-001A` / $0.00 / Tags: *(blank)* | Looks clean — same format (DVD), same likely type (Rental). Row 2 just needs Tags copied. |
| `finding-dory` | `50%` / `001A` / barcode `191-BLRFND-50-001A` / $0.00 / Tags: `Kids & Family` | `Standard` / `002A` / barcode `191-BLRFND-002A` / $0.00 / Tags: *(blank)* | Looks clean — same format (Blu-Ray). Neither row has a Rental/Floor Sale tag though — both would still need a type tag added. |
| `night-of-the-living-dead` | `50%` / `001A` / barcode `191-BLRNGH-50-001A` / $0.00 / Tags: `Horror, Rental` | `Standard` / `002A` / barcode `191-BLRNGH-002A` / $0.00 / Tags: *(blank)* | Looks clean — same format (Blu-Ray), same type (Rental). Row 2 just needs Tags copied. |
| `a-million-to-juan` | `Standard` / `001A` / barcode `191-VHSAMI-001A` / $0.00 / Tags: `Comedy, Floor Sale` | `Standard` / `002A` / barcode `191-VHSAMI-002A` / $4.00 / Tags: *(blank)* | Row 1 is tagged Floor Sale but priced $0 (invalid alone). Row 2 has the real-looking $4 price but no tags. Likely the tags and price are on the wrong rows, or the two copies are actually different types. |
| `get-shorty` | `50%` / `001A` / barcode `191-VHSGET-50-001A` / $0.00 / Tags: `Comedy, Floor Sale` | `Standard` / `002A` / barcode `191-VHSGET-002A` / $4.00 / Tags: *(blank)* | Same pattern as `a-million-to-juan`. |
| `outrageous-fortune` | `50%` / `002A` / barcode `191-VHSTRG-50-002A` / $5.00 / Tags: `Comedy, Floor Sale` | `50%` / `001A` / barcode `191-VHSTRG-50-001A` / $0.00 / Tags: *(blank)* | Row 1 looks like a valid Floor Sale copy. Row 2 has no tags and $0 — could be a second Floor Sale copy missing its price, or a Rental copy missing its tag. |
| `speed-racer` | `50%` / `001A` / barcode `191-BLRSPE-50-001A` / $0.00 / Tags: `Kids & Family, Rental` | `Standard` / `001A` / barcode `191-DVDSPE-001A` / $0.00 / Tags: *(blank)* | **Not actually a duplicate-copy case** — barcode prefixes differ: `BLR` (Blu-Ray) vs `DVD` (DVD). Two different formats are incorrectly sharing one handle; per catalogue convention (one product per movie+format) these should never have been merged. |

## Recommendation once reviewed

For the 3 "clean" ones (`royal-tenenbaums`, `finding-dory`, `night-of-the-living-dead`): confirm the type/genre to apply to the blank row, then split into two separate products with distinct handles (e.g. append the barcode suffix).

For `a-million-to-juan`, `get-shorty`, `outrageous-fortune`: need a decision on which row gets which type/price — likely requires checking the physical items or original inventory record.

For `speed-racer`: needs to be split by *format*, not just copy — likely two separate products, one Blu-Ray one DVD, each getting its own genre/type tags from scratch.
