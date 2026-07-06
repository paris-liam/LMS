# Supercycle build progress

Running log of Supercycle feature work, kept in sync as we build. Each entry lists what changed in the repo, what still needs doing in Shopify admin/theme editor, and any judgment calls or open questions.

See also: `lms-supercycle-feature-plan.md` (full feature plan + buildability index) and `CLAUDE.md` (store/theme reference, integration contract).

---

## 2026-07-05 — "Join the club" buttons (header + hero), gated on membership status

**Repo changes:**
- `sections/header.liquid` — added the schema settings (`enable_membership_gating`, `join_club_url`, `join_club_label`) that `snippets/header-actions.liquid` already had gating logic for but couldn't use, since the settings didn't exist yet. The button now actually appears in the header account slot for non-members.
- `snippets/header-actions.liquid` — updated a stale comment; the `Has active subscription` tag is now applied live by Supercycle, not a manually-applied test stand-in.
- `sections/lms-hero.liquid` — added a `hide_if_member` checkbox to the hero's generic `button` block schema (not specific to "Join the club" — any hero button can opt into hiding for members). The "Join the club →" preset button has it on by default. Visibility is resolved with a manual counting loop rather than the `where_exp` filter, which `shopify theme check` flagged as unsupported in this theme.
- Both header and hero gate the same way: `customer.tags contains 'Has active subscription'`.

**Shopify admin / theme editor — outstanding:**
- [ ] Theme editor → Header section → set **Join the club link** to the membership page, confirm the label.
- [ ] Theme editor → Hero section → the "Join the club →" button block has "Hide for members" checked already; set its **Link** to the membership page.
- [ ] Test: tag a test customer with `Has active subscription`, view the site logged in as them, confirm both buttons disappear.

**Open question / judgment call:**
- Currently only `Has active subscription` hides the buttons. `Has paused subscription` customers still see "Join the club" — undecided whether a paused member should count as "already a member" and also have it hidden. Flag if you want that changed.

---

## Template for new entries

```
## YYYY-MM-DD — <feature>

**Repo changes:**
- ...

**Shopify admin / theme editor — outstanding:**
- [ ] ...

**Open question / judgment call:**
- ...
```
