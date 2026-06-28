# Little Movie Store — Design System

> Meet me at the movie store.

A warm, lived-in brand system for **Little Movie Store (LMS)** — a physical-media movie shop and membership community on Passyunk Ave in South Philadelphia. Sells used & new DVD, Blu-ray, 4K, and VHS, plus boutique/collector titles, merch, snacks, and media-player rentals. The business runs on three legs: **in-store retail, online (weekly drops, mystery bags, rare finds), and the $100/year Little Movie Club membership.** The website's #1 job is to **sell memberships** and feel like the store: welcoming, calm, cute, simply designed.

Brand archetype: **50% Explorer / 25% Caregiver / 25% Sage.** Core values: **warmth, curiosity, belonging.** "Care > cool. Ritual experience > retail experience. Sense of belonging > traditional customer service."

## Sources provided
- `uploads/Little Movie Store Brand Book.pdf` — logos, monograms, typography, color palette, tone & voice, audience personas, archetype. **Primary brand reference.**
- `uploads/Little Movie Store _ Website Notes.pdf` — website plan: pages, homepage sections, Genre Mode concept, timeline, and direct corrections to an earlier draft ("use Parchment", "use Brick", "correct logo", "make hero a GIF").
- `uploads/Little Movie Store.pdf` — the investor deck (business model, financials, three-year outlook). Drives the **sample slides** voice.
- Logo + monogram SVGs (horizontal, stacked, stacked-with-tagline; Circles, Looped, Tape) — copied into `assets/`.

No codebase or Figma file was provided; the system is built from the brand book + notes.

---

## CONTENT FUNDAMENTALS — how LMS writes

**Voice:** friendly, excited, knowledgeable, a little cheeky. Warm and human, never corporate or salesy. "Helpful, genuine, and open for questions, rather than authoritative and sales-driven." Typography that feels *written for people, not engineered for interfaces.*

**Person:** Mostly **"we"** (the store, a real group of movie lovers) speaking to **"you"** (a welcomed guest). Inclusive, conversational. "We really love movies, and we want to share that with our community."

**Casing:** Headings are **Sentence case** (per brand book), e.g. *"Built by movie lovers."* The investor deck uses bold uppercase statements for impact — reserve all-caps for eyebrow labels and big poster-style statement moments.

**Tone examples (real copy from the materials):**
- "Meet me at the movie store." (tagline)
- "Be our borrow buddy!"
- "Renters become buyers. That's the whole game, baby!"
- "We're so back."
- "Movies you can feel."
- "Built by movie lovers, for everyone."
- "A store to explore."
- Sub-collection names are clever & specific: *Comedy → "Films From the 90s Set in the 70s"*, *Holiday → "Safe Movie Choices for When Your In-Laws Visit."*

**Cheeky but kind.** Playful asides ("baby!", "stoked"), but the underlying message is always reassuring and low-pressure. Discovery over transaction. Every shelf has a hand-written note; every receipt might get a little smiley face.

**Emoji:** Not part of the brand. Avoid emoji in UI. The brand *does* use a small set of **typographic marks** as decoration — a `✦` sparkle, occasional `:)` in headers (the deck signs off "THANK YOU :)"), and the `←`/`›` arrows. Keep these sparing and charming, not loud.

**Do:** invite, recommend, explain *why* something belongs. **Don't:** gatekeep, oversell, talk down. "We are not snobby and we don't gatekeep."

---

## VISUAL FOUNDATIONS

**Mood:** vintage, warm, lived-in — like a well-curated second-hand store. Exposed brick, wood panelling, a worn flannel, soft light. "Textures and colours you'd choose for your home, not a screen." Designed to feel *not too polished* but still clever and playful.

**Color** (see `tokens/colors.css`):
- **Primary:** Brick `#973123` (exposed-brick red, the main accent) and Mahogany `#3A2018` (deep wood brown — the brand's ink/dark surface).
- **Secondary:** Sage `#5F8D7A`, Hunter `#343A31` (grounded greens), Parchment `#FFF9EF` (the default warm-paper background), Soft Cyan `#8FCDCF` (the light, bright accent).
- **Backgrounds are parchment by default**, never pure white; cards are warm white. Dark sections use mahogany, hunter, or brick.
- Logo color pairings stay **tonal / low-contrast** — opt for quiet combinations, not high-contrast clashes.

**Type** (see `tokens/typography.css`):
- **Epilogue** for headings (Sentence case, 0 tracking). H1 = Medium 30pt, H2 = Regular 25pt.
- **DM Mono** for body and the signature eyebrow. Body = DM Mono Light 16/13. **Eyebrow = DM Mono Medium 12pt, ~0.22em tracking, UPPERCASE** — the most recognizable type element in the system.
- The mono body voice is deliberate: it reads as typewritten, personal, human — not interface-engineered.

**Backgrounds & texture:** flat warm color fields (parchment, brick, mahogany, hunter), not gradients. Brand personality comes from the **monogram marks** drifting subtly in hero/poster moments and the **scrolling product ticker**, not from decorative gradients or noise. (A light radial warmth on the hero "screen" is acceptable; avoid bluish/purple gradients entirely.)

**Borders & cards:** soft 1.5px warm hairline borders (`--border-default`, a parchment edge), generous radii (`--radius-lg` 18px for cards, `--radius-pill` for buttons/tags). Cards = warm white, hairline border, low warm-tinted shadow. Nothing sharp; nothing harsh.

**Shadows:** soft, low, and **warm-tinted** (mahogany rgba), like objects resting on a shelf — never cool gray drop-shadows. See `--shadow-xs…lg`.

**Radii:** gentle and friendly. Buttons and tags are fully pill-shaped; surfaces use 12–18px.

**Motion:** calm and gentle. Soft easing (`--ease-soft`), short durations (140–420ms). Monograms float slowly; the ticker marquees; no aggressive bounces or springy overshoot. Respect a slow, "slow people down" pace.

**Hover states:** buttons brighten slightly (`brightness(1.06)`); product cards lift `translateY(-4px)`; links shift toward cyan on dark. **Press states:** buttons shrink subtly (`scale(0.97)`). Inputs gain a sage border + soft sage focus ring.

**Imagery vibe:** warm, nostalgic, film-forward. Movie covers, VHS spines, the physical store. (No real cover art was supplied — product cards use brand-color "poster" placeholders; swap in real artwork via `ProductCard`'s `image` prop.)

**Layout:** centered max-width container (`--container-max` 1200px), comfortable section padding (~76px vertical). Sticky translucent parchment header with backdrop blur. Generous whitespace — the space should feel calm, "more like a café than a collector's cave."

---

## ICONOGRAPHY

LMS has **no icon font or large icon set** in the provided materials. The iconographic language is the **three brand monograms** plus a few restrained typographic marks.

- **Monograms** (`assets/monograms/`): **Circles**, **Looped**, and **Tape** — expressive L·M·S marks. Used *sparingly* and as a secondary device (stickers, packaging details, hero/poster accents), always near a primary logo or where the brand is already recognizable. Black originals + `*-current.svg` versions that inherit `currentColor` for tinting onto brand backgrounds.
- **Logos** (`assets/logos/`): horizontal, stacked (primary), and stacked-with-tagline (for "introducing" moments). Black + `*-current.svg` tintable versions. Keep `O`-character padding around logos; never recolor outside approved pairings; never skew, squish, or re-space.
- **Typographic marks:** a `✦` sparkle as a bullet/divider, `←` `›` arrows for nav, occasional `:)`. No emoji.
- **Functional UI icons:** none were provided. If a screen genuinely needs interface glyphs (search, cart, close), substitute a lightweight CDN line set such as **Lucide** (`https://unpkg.com/lucide-static`) at ~1.5px stroke to match the hairline borders — **flagged as a substitution**, not part of the official brand. Prefer text labels and monograms where possible.

⚠️ **Substitution flags:** (1) UI glyphs are not defined by the brand — Lucide is a stand-in if needed. (2) Fonts (Epilogue, DM Mono) are served from Google Fonts' CDN; if you have licensed binaries, drop them in and point `tokens/fonts.css` at them.

---

## INDEX — what's in this system

**Root**
- `styles.css` — the single entry point consumers link. `@import`s all tokens + fonts.
- `readme.md` — this guide.
- `SKILL.md` — Agent-Skills-compatible front matter for download/use in Claude Code.

**`tokens/`** — `colors.css`, `typography.css`, `spacing.css` (radii/shadows/motion/layout), `fonts.css` (@font-face for Epilogue + DM Mono).

**`assets/`** — `logos/` (horizontal, stacked, stacked-tagline; black + currentColor), `monograms/` (circles, looped, tape; black + currentColor).

**`components/`** — reusable React primitives (namespace `window.LittleMovieStoreDesignSystem_a217bb`):
- `core/`: **Button** (primary/secondary/sage/outline/ghost), **Badge** (format & status tags), **Eyebrow** (the signature label), **Input**, **Card**.
- `commerce/`: **ProductCard** (movie/media shelf item).

**`ui_kits/`**
- `website/` — interactive storefront: Home, Shop, Product, Join the Club, with Header (incl. Genre Mode), Ticker, Newsletter, Footer. Entry: `ui_kits/website/index.html`.
- `deck/` — five sample slides (Title, Chapter, Three-Column, Big Statement, Stat) in the investor-deck voice + a key-nav presenter (`index.html`).

**`guidelines/cards/`** — foundation specimen cards (Type, Colors, Spacing, Brand) shown in the Design System tab.
