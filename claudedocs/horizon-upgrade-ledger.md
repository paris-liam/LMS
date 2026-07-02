# Horizon 3.5.1 → 4.1.1 upgrade — customization ledger

Generated 2026-07-02 on branch `feat/horizon-upgrade`.

This is the complete inventory of every change made to stock Horizon 3.5.1 in
`theme/lms-redesign/`, produced by diffing against the pristine baseline in
`theme/horizon-baseline-3.5.1/` (upstream commit `45c7db58`, whitespace-only and
store-injected-comment noise excluded).

**Carry-over target**: `theme/lms-redesign-v4/` — pristine Horizon 4.1.1
(upstream commit `97f7fae1`), committed untouched so `git diff` against that
commit is the v4 customization inventory going forward.

Full unified diff of all modified files: `claudedocs/horizon-351-customizations.patch`

---

## A. Added files (copy over, then refactor against 4.1.1 conventions)

Check each for references to removed 3.x systems — especially `color-scheme-*`
classes and any `--color-*` variables that changed under the new palette system.

| File | Notes |
|---|---|
| `assets/lms-tokens.css` | Design system tokens. Re-verify every Horizon variable it overrides still exists in 4.1.1 (`--font-*--family`, `--color-primary`, `--color-success`, `--border-width`). `theme.liquid` load point must be re-added (see B). |
| `assets/dm-mono-300.woff2`, `dm-mono-400.woff2`, `dm-mono-500.woff2` | Self-hosted body font |
| `assets/epilogue-variable.woff2` | Self-hosted heading font |
| `assets/lms-logo-horizontal-brick.svg`, `lms-logo-stacked.svg`, `lms-logo-stacked-tagline-parchment.svg` | Brand logos |
| `sections/coming-soon.liquid` | **The live password page.** LightWidget embed, DVD-bounce animation — see CLAUDE.md for constraints |
| `sections/lms-hero.liquid` | |
| `sections/lms-new-releases.liquid` | |
| `sections/lms-staff-picks.liquid` | |
| `sections/lms-promo-pair.liquid` | |
| `sections/lms-events-membership.liquid` | |
| `sections/social-bar.liquid` | |
| `blocks/lms-promo-card.liquid` | |
| `snippets/lms-eyebrow.liquid` | |
| `snippets/lms-product-card.liquid` | |

Note: `sections/lms-homepage-hero.liquid` appears in git history but is not in
the current working tree — it was superseded; do not resurrect.

## B. Modified stock files (re-apply edits onto fresh 4.1.1 files)

Diffs in `horizon-351-customizations.patch`. Upstream also changed all of these
between 3.5.1 and 4.1.1, so apply by hand/inspection — do not blind-apply the patch.

| File | Size of our edit | What it is |
|---|---|---|
| `layout/theme.liquid` | +1 | Single line: load `lms-tokens.css` after theme styles. In 4.1.1 the style pipeline is `stylesheets` → `theme-styles-variables` → `color-palette` (color-schemes snippet is GONE); insert after `color-palette`. |
| `layout/password.liquid` | +1/−4 | Small edit for the coming-soon page |
| `blocks/_header-logo.liquid` | +48/−10 | Header logo work |
| `blocks/logo.liquid` | +16/−4 | Logo block work |
| `blocks/_header-menu.liquid` | +6/−1 | |
| `snippets/header-actions.liquid` | +74/−48 | Largest code edit |
| `snippets/header-drawer.liquid` | +73/−0 | Note: 4.1.1 adds a new `theme-drawer.js` / drawer system — reconcile carefully |
| `sections/footer.liquid` | +5/−0 | |
| `sections/footer-utilities.liquid` | +2/−2 | |

## C. Data / settings files (rebuild, not merge)

| File | Size | Migration note |
|---|---|---|
| `config/settings_data.json` | +264/−236 | **Does not port.** 3.x color schemes were removed in 4.0 — rebuild as the new `color_palette` + `palette_*` settings (being done with the other agent). Font pickers, button radius (`button_border_radius_*`), and type presets need re-mapping against the 4.1.1 `settings_schema.json`. |
| `sections/header-group.json` | +50/−12 | Rebuild on 4.1.1 defaults; `color_scheme` keys are obsolete |
| `sections/footer-group.json` | +309/−89 | Same — this one has substantial custom footer composition |
| `templates/index.json` | +581/−227 | Homepage composition (lms-* sections). Sections carry over; per-section `color_scheme` settings must be replaced per the 4.x model |
| `templates/password.json` | +2/−122 | Points at `coming-soon` section |
| `templates/page.json`, `page.contact.json` | +79/−2, +21/−5 | |
| `templates/product.json` | +18/−16 | |
| Other templates (404, article, blog, cart, collection, list-collections, search) | small | Mostly scheme/setting tweaks — review individually |

## D. Excluded noise (do NOT carry over)

- 49 `locales/*.json` diffs — store-injected "auto-generated" comment headers only
- `config/settings_schema.json` — whitespace-only after normalization
- ~120 blocks/sections whitespace-only diffs from store pull normalization
- `.DS_Store`, `.claude/` inside the theme dir

## Suggested order of work

1. ✅ Vendor baselines, generate this ledger
2. Other agent: palette/typography/settings on pristine `lms-redesign-v4` (settings_data.json + lms-tokens.css rebuilt against the 4.1.1 variable inventory)
3. Copy A-files, refactor each against 4.1.1
4. Re-apply B-edits by hand using the patch as reference
5. Rebuild C-files (templates/groups) in the 4.x settings model
6. Push `lms-redesign-v4` to dev store as a NEW unpublished theme; QA side-by-side vs theme `140897157182`
7. At parity: switch working-theme ID, delete `theme/lms-redesign/` and `theme/horizon-baseline-3.5.1/`
