# LMS theme — Shopify CLI cheat sheet

Project values used below:

- **store** = `p0wkgv-wy.myshopify.com` (always the `.myshopify.com`, never the custom domain)
- **WIP theme** = `164180295930` ("LMS Redesign (WIP)")
- **live theme** = `161348780282` (Horizon — never push here without client sign-off)
- **path** = `theme/lms-redesign`

---

## 🟢 Starting a new feature

```bash
# 1. Confirm where you are / clean tree
git status && git branch

# 2. Branch off for the feature (never work on main)
git checkout -b feat/<short-name>

# 3. Pull the store's current state so local matches any theme-editor edits
shopify theme pull --path theme/lms-redesign --store p0wkgv-wy.myshopify.com --theme 164180295930
git add -A && git commit -m "Sync: pull live theme before <feature>"   # only if it changed

# 4. Live local preview with hot reload (run in your own terminal; long-running)
shopify theme dev --path theme/lms-redesign --store p0wkgv-wy.myshopify.com
```

**Why pull first:** the client edits content in Shopify's theme editor (color schemes, section
blocks, settings). Pulling first means your local copy includes those edits, so a later push
won't silently overwrite them.

---

## 🔵 Before you push

```bash
# 1. Lint the theme (Liquid / JSON / schema errors)
shopify theme check --path theme/lms-redesign

# 2. Review and commit your changes
git status && git diff
git add -A && git commit -m "<what changed>"

# 3. Pull again (catch edits made on the store since you started)
shopify theme pull --path theme/lms-redesign --store p0wkgv-wy.myshopify.com --theme 164180295930

# 4. Push — narrowly, only the files you changed
shopify theme push --path theme/lms-redesign --store p0wkgv-wy.myshopify.com --theme 164180295930 \
  --only sections/coming-soon.liquid --only assets/lms-tokens.css
```

**Why `--only`:** avoids re-pushing store/app-managed templates (`templates/product.json`,
`config/settings_data.json`). Pushing those back up is what caused the Supercycle `block_order`
push failure (see the orphaned-block gotcha below).

### Optional pre-push integrity check (block_order ⊆ blocks)

Catches dangling app-extension block references before they fail `theme push`:

```bash
cd theme/lms-redesign && python3 - <<'PY'
import json, glob
def walk(n, p, out):
    if isinstance(n, dict):
        if isinstance(n.get('block_order'), list):
            defined = set((n.get('blocks') or {}).keys())
            for b in n['block_order']:
                if b not in defined: out.append((p, b))
        for k, v in n.items(): walk(v, p+'/'+str(k), out)
    elif isinstance(n, list):
        for i, v in enumerate(n): walk(v, p+f'[{i}]', out)
out=[]
for f in sorted(glob.glob('templates/*.json')):
    raw=open(f).read(); walk(json.loads(raw[raw.index('{'):]), f, out)
print("orphans:", out if out else "NONE")
PY
```

---

## 🔑 Command + option reference

| Command | What it does |
|---|---|
| `shopify theme list` | Show all themes + ids + which is `[live]` |
| `shopify theme pull` | Download theme files from the store → local |
| `shopify theme push` | Upload local files → a theme on the store |
| `shopify theme dev` | Local server at `127.0.0.1:9292` with hot reload (proxies real store data) |
| `shopify theme check` | Static linter for the theme |

| Option | Meaning |
|---|---|
| `--store <domain>` | Which store (always the `.myshopify.com`) |
| `--theme <id>` | Target a specific theme by id (omit on push with `--unpublished` to create a new one) |
| `--path <dir>` | Theme folder to operate on (ours is in a subfolder) |
| `--only <pattern>` | Push/pull **only** matching files (repeatable) |
| `--ignore <pattern>` | Push/pull everything **except** matching files (e.g. `--ignore templates/product.json`) |
| `--unpublished` | (push) create a new unpublished theme |
| `--live` | (push) target the published theme — **don't use until client-approved go-live** |
| `--nodelete` | (push) don't delete remote files missing locally — safer for scoped pushes |
| `--json` | Machine-readable output (handy to grab a new theme id) |

---

## ⚠️ Hard rules

- **Pull before push.** Always.
- **Push code with `--only`;** let `config/settings_data.json` + `templates/*.json` be managed on
  the store unless you intentionally changed them.
- **Never `--live`** without explicit go-ahead.
- If a full push errors on a `block_order` / app block, it's a dangling app-extension reference
  (a Supercycle app block left orphaned by `theme pull`). Run the integrity check above, remove
  the orphaned id from `block_order`, or push scoped with `--only` — don't guess at app-block defs.
- `shopify theme dev` / `theme pull` / `theme push` need an interactive terminal (auth + the
  storefront password prompt); they don't run well in non-interactive/CI contexts.
