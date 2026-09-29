# Running `libib selftest` on GitHub Actions

The daily Libib health check runs as a **scheduled Claude Code cloud session**
(set up 2026-09-29). These are the instructions for running the same check on
GitHub Actions instead, or as well. Nothing here is set up yet.

`python3 -m catalog libib selftest` is read-only: it logs into Libib, walks
every page step the fixer, export and import use, and never saves or imports
anything (see `catalog/README.md`, Stage 4). It exits 1 and names the broken
step when Libib's pages have changed.

## 1. Add the Libib login as repository secrets

The repo is **public** — the login must only ever live in Actions secrets,
never in a file.

GitHub → `paris-liam/LMS` → Settings → Secrets and variables → Actions →
**New repository secret**, twice:

| Name | Value |
|---|---|
| `LIBIB_EMAIL` | the Libib account email |
| `LIBIB_PASSWORD` | the Libib account password |

Secrets are not passed to workflows triggered by pull requests from forks, so
a stranger's PR can't read them.

## 2. Add the workflow

Create `.github/workflows/libib-selftest.yml`:

```yaml
name: Libib selftest

on:
  schedule:
    - cron: "17 13 * * *"      # daily 13:17 UTC; GitHub cron is always UTC
  workflow_dispatch:            # plus a "Run workflow" button in the Actions tab

permissions:
  contents: read

concurrency:
  group: libib               # never two Libib logins at once from Actions
  cancel-in-progress: false

jobs:
  selftest:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Playwright + Chromium
        run: |
          python -m pip install playwright
          python -m playwright install --with-deps chromium

      - name: Libib selftest (read-only)
        env:
          LIBIB_EMAIL: ${{ secrets.LIBIB_EMAIL }}
          LIBIB_PASSWORD: ${{ secrets.LIBIB_PASSWORD }}
        run: python -m catalog libib selftest
```

Commit it to `main`; scheduled workflows only run from the default branch.

Notes:

- `scripts/cloud-setup.sh` is **not** needed here: its proxy-CA and PPA
  workarounds are for the Claude cloud sandbox. GitHub runners reach Libib
  directly; `playwright install --with-deps` covers Chromium's libraries.
- The item it exercises is the first `done` entry in `libib-sync/_state.json`
  (checked out with the repo). Pass `--call-number <n>` to pin one.
- Failure screenshots land in `libib-selftest/`. They are **not** uploaded as
  an artifact on purpose: Actions artifacts on a public repo can be downloaded
  by any signed-in GitHub user, and the screenshots show Libib's pages. To see
  them, re-run the check in a Claude cloud session instead.

## 3. Get told when it fails

A failed run turns the workflow red and GitHub emails whoever last edited the
workflow file (Settings → Notifications → Actions: "Send notifications for
failed workflows only"). Nothing else is needed for an alert.

## 4. Check it works

Actions tab → **Libib selftest** → **Run workflow**. A healthy run ends with:

```
OK: all 9 steps work.
```

## Caveats

- **Libib may challenge logins from GitHub's servers.** Its login is plain
  email/password today, but a new machine or IP range can trigger a
  verification step. If the first run fails at `login` while the cloud-session
  check passes, that is the likely cause; the cloud session is then the only
  reliable runner.
- **One Libib writer at a time.** The selftest only reads, but it still logs
  in. The `concurrency` group keeps Actions runs from overlapping each other;
  avoid scheduling it at the same time as the daily cloud-session check or a
  `libib sync`.
- Scheduled workflows in a repo with no activity for 60 days are disabled by
  GitHub automatically; re-enable from the Actions tab.
