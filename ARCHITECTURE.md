# UCI Calendar — Architecture & Operations Guide

## Overview

A Progressive Web App (PWA) showing live UCI men's road race results, upcoming races, team rosters, rider profiles, statistics, and a fantasy league. Data is scraped from **cyclingflash.com** (race results/startlists) and **procyclingstats.com** (rider profiles, specialty scores, career wins), stored in `data.json` and `rider_profiles.json`, and served via **GitHub Pages** at `https://psykalist.github.io/UCI-Calendar/`.

---

## Data Flow

```
cyclingflash.com ──► scraper.py ──────────────────► data.json ──► GitHub Pages ──► index.html (PWA)
                                                         │
procyclingstats.com ─► scrape_rider_profiles.py ──► rider_profiles.json ──────────────────────────►┘
procyclingstats.com ─► scrape_pcs_stats.py ──────► pcs_stats.json ───────────────────────────────►┘
procyclingstats.com ─► scrape_palmares.py ───────► palmares.json ────────────────────────────────►┘
```

---

## Scripts

### `scraper.py` — core data scraper

Four modes. Only `--results-only` runs automatically (CI). All others run locally.

**`py scraper.py --results-only`** (CI + daily scheduled task)
Fetches new stage results and classifications for live races only. Auto-promotes upcoming → live and live → recent by date. Refreshes career wins for today's stage winners (~1–3 PCS requests). Does NOT re-scrape teams, calendar, or startlists.

**`py scraper.py --teams-only`** (manual, local)
Refreshes WorldTeam + ProTeam rosters from cyclingflash.com. Run mid-season after transfers. Does NOT embed wins in teams data (those stay in `rider_profiles.json`). Output: updates `data.json` teams section only.

**`py scraper.py --startlists-only`** (daily scheduled task, local)
Fetches PCS startlists for upcoming/live races that don't have one yet. PCS blocks CI IPs so this must run locally. Startlists are published 2–7 days before race start.

**`py scraper.py`** (full scrape — manual, local, start of season only)
Full calendar discovery, team scrape, rider profile backfill (up to 50 new riders), startlists. Run at season start or when the race calendar changes significantly.

**Women's race guard:** the scraper filters out women's races by UCI category (`1.WWT`, `2.WWT`, etc.) and by name keywords. The CI workflow has an additional post-scrape strip step as a belt-and-braces check.

**Key behaviour:**
- All writes use atomic tmp-file replace to prevent corruption
- Post-write validation checks file size and JSON validity; restores backup on failure
- Uses `git pull --rebase` + retry on push rejection (for `--update-winners` mode)

---

### `scrape_rider_profiles.py` — rider profiles from PCS

Builds and maintains `rider_profiles.json` (~4–5 MB, ~1800 riders) with photo, DOB, nationality, height/weight, specialty scores, and full career wins.

**Modes:**
- Default: fetches profiles for new riders only (not yet in JSON)
- `--fix-empty`: re-fetches riders with 0 wins (may have been blocked first time)
- `--all`: re-fetches every rider
- `--update-winners`: fetches only today's stage winners + GC leaders; auto git commit + push

**`--update-winners`** runs via Cowork scheduled task at 8pm daily. Used to keep winner palmares current after race days.

**Data sources:**
- Main rider page (`/rider/{slug}`): photo, bio block (DOB, height, weight, nationality, specialty scores)
- Wins page (`/rider/{slug}/statistics/wins`): full career palmares table

**Output format (`rider_profiles.json`):**
```json
{
  "scraped_at": "...",
  "count": 1800,
  "riders": {
    "tadej-pogacar": {
      "name": "Tadej Pogačar",
      "nat": "si", "nat_name": "Slovenia",
      "photo": "https://...",
      "dob": "1998-09-21",
      "height": 1.76, "weight": 65,
      "specialties": { "gc": 95, "oneday": 89, "climber": 92, "sprint": 61, "tt": 78, "hills": 80 },
      "wins": [{ "year": "2024", "date": "2024-07-21", "race": "Tour de France - Stage 21", "cat": "2.UWT" }]
    }
  }
}
```

---

### `scrape_pcs_stats.py` — PCS statistics tables

Scrapes all statistics pages from procyclingstats.com (most wins, best climbers, sprinters, etc.) and saves to `pcs_stats.json`. Powers the **Stats tab** in the app.

**Usage:** `py scrape_pcs_stats.py` (manual, run monthly or when stats need refreshing)

---

### `scrape_palmares.py` — historical winner lists (Historical tab)

Scrapes year-by-year top-3 podiums from each race's `procyclingstats.com/race/{slug}/results/palmares` page and saves to `palmares.json`. Covers the ~29-race PCS taxonomy (Grand Tours, Major Tours, Monuments, Championships, Top Classics). Powers the **Historical tab** inside the Stats section.

The page markup is a `<ul class="palmares">` list, not a `<table>` — an earlier version of this parser assumed a table (matching the pattern used elsewhere by `scrape_pcs_stats.py`) and silently returned 0 editions for every race until this was caught and fixed.

For stage races (Grand Tours + Major Tours) this also fetches the Points, Mountains (KOM), and Young Rider classification podiums — found via PCS's `race.php?race={internal_id}&gctype={5|7|6}` URL, using the numeric race ID scraped off the GC page's filter form (the pretty `/results/palmares` URL ignores a `?gctype=` query param, it only works through this internal form endpoint). One-day races (Monuments, Championships, Top Classics) only have the one podium. Each rider entry also carries their nationality flag code (`nat`), rendered via the app's existing `flag()` helper.

**Usage:**
```
py scrape_palmares.py              # fetch races missing from palmares.json
py scrape_palmares.py --all        # re-fetch every race, overwrite existing
py scrape_palmares.py --race giro-d-italia   # fetch/refresh one race only
py scrape_palmares.py --list       # print the race registry and exit
```

Must be run locally — PCS blocks CI/cloud IPs, same restriction as `scrape_pcs_stats.py`. Saves incrementally after each race so a crash partway through doesn't lose earlier progress.

---

### `detect_changes.py`

Diffs old vs new `data.json` and writes notable changes to `changelog.json` (stage wins, GC leader changes, jersey changes, startlist additions). Entries older than 14 days are pruned. Called by CI after every scraper run.

---

### `heal.py` — local watchdog

Run every 5 minutes via Windows Task Scheduler.

**Checks and repairs:**

| Check | Auto-repair |
|-------|-------------|
| `.git/index.lock` / `HEAD.lock` present | Delete them |
| `data.json` too small or invalid JSON | `git checkout HEAD -- data.json` |
| Specialty coverage below threshold | Applies `specialty_cache.json` entries if available |
| `index.html` too small / missing `</html>`, `</script>` / JS syntax error (via `node --check`) | Reports only |
| Local branch behind origin/main | Warn only |

**Usage:**
```
py heal.py          # check + repair
py heal.py --push   # also commit + push status.json
py heal.py --status # print current status.json and exit
```

> **Known bug (2026-07-08):** `check_git_sync()` references an undefined variable (`r2`) and raises `NameError` on every run, before `write_status()`/`flush_log()`/`--push` ever execute — see `CODE_REVIEW.md` for details and the fix. Until patched, `heal.py` is not actually writing `status.json` or pushing anything locally; the CI-side `health-check.yml` watchdog is currently the only one actually running end-to-end.

---

### `scrape_cyclingoracle.py`

Fetches CyclingOracle's 13-attribute (0–100 scale) rider ratings via their GraphQL API and merges them into `rider_profiles.json` as `co_stats` on each rider. This is the scoring input for `generate_best_teams.py`'s Team Claudius squads — NOT the same thing as PCS "specialties" (those are unnormalised cumulative career points, not comparable). Matches CyclingOracle names to existing PCS slugs via exact + prefix matching; creates a minimal CO-only profile entry when no PCS match is found. Run weekly via `update-co-stats.yml` (Monday 6am UTC).

---

### `generate_best_teams.py`

Builds `best_teams.json` — one AI-opponent squad ("Team Claudius") per race, scored from `co_stats` and picked via an exact 0/1 knapsack (not greedy value/cost-ratio — see the file's docstring for why that matters). Run automatically by `scrape.yml` after every results-only scrape.

---

## Scheduled Tasks (Cowork)

Three tasks run automatically while the Cowork app is open:

| Time | Task | What it does |
|------|------|--------------|
| 9am daily | `uci-startlists-daily` | `py scraper.py --startlists-only` — fetches new startlists from PCS |
| 8am / 2pm / 8pm daily | `uci-calendar-daily-update` | `py scraper.py --results-only` — fetches stage results |
| 8pm daily | `uci-winner-profiles` | `py scrape_rider_profiles.py --update-winners` — refreshes winner profiles |

---

## GitHub Actions Workflows

All git-writing workflows share `concurrency: group: uci-calendar-git-write` (cancel-in-progress: false) so they never commit/push to `main` at the same time — added after a 2026-07-02 through 2026-07-05 incident where two racing pushes caused a rejected push + failed rebase retry that silently dropped a freshly-scraped `data.json`. **Exception:** `update-co-stats.yml` is currently missing this — see `CODE_REVIEW.md`.

### `scrape.yml` — "Pull Race Results" (primary, runs on self-hosted runner)
Twice daily. Runs `scraper.py --results-only` then `scraper.py --startlists-only`, strips any women's races that slipped through, runs `detect_changes.py`, regenerates `best_teams.json` via `generate_best_teams.py`, then commits `data.json` + `changelog.json` + `best_teams.json` (+ `scrape_log.json` if present).

**Schedule:** 11am UTC and 5pm UTC daily (12pm and 6pm BST).

**Reachability check:** before scraping, fetches a real cyclingflash.com race page with a full browser-like header set and requires >500 bytes back — this replaced an earlier check that hit a dead legacy endpoint and always looked "unreachable" regardless of actual site status.

**`scrape_log.json`:** written by `main_results_only()` in `scraper.py` on every run. Records, per live race, whether the next expected stage page fetched OK and whether a results table was found — lets `health-check.yml` distinguish "stage genuinely hasn't finished yet" from "scraper ran, exited 0, and is silently blind to a page that has results" (`possible_parser_drift`, flagged after 5+ consecutive stalls spanning 48+ hours on the same stage). Was 2 attempts/10h until 2026-07-10, which false-positived on essentially every stage of a Grand Tour — scrape.yml only runs at 11am/17:00 UTC, and consecutive stages finish around the same time of day, so the very next scrape after one stage finishes is routinely 16-20h into "stalled" on the next stage before it's even happened; a rest day stretches that normal gap to ~42-48h. 48h/5 attempts sits above the longest normal (rest-day) gap. The blunter `data_age_hours` staleness check below still catches a scraper that's stopped working entirely, on a shorter fuse.

**Trigger manually:** GitHub → Actions → "Pull Race Results" → Run workflow.

### `health-check.yml` — watchdog (runs on `ubuntu-latest`)
Triggered by: push to `status.json`, `workflow_run` completion of `scrape.yml` or `update-data.yml` (success *or* failure — catches a scrape that ran and found nothing without waiting up to 6h for the next cron tick), a 6-hourly schedule, or manual dispatch (with a `force_scrape` input).

Reads `status.json` + `data.json` age to decide whether to re-run the scraper itself (`--results-only`, since this runs on a GitHub-hosted IP, not the self-hosted runner — cyclingflash.com reachability is checked the same way as `scrape.yml`). Staleness thresholds are **live-race-aware**: 8h stale-trigger / 20h error / 8h warning while `data.json` has any live race, vs. 26h / 168h / 48h off-season (tightened 2026-07-07 after a stage-4 result sat 24.6h old and still read as "fresh" under the old flat thresholds). Also parses `scrape_log.json` — `fetch_ok: false` entries become warnings, `possible_parser_drift` entries become errors naming the race/stage/stall duration.

Restores `data.json` from the last good git commit if it's missing, too small, or invalid JSON. Writes its own `status.json` (source: `"ci"`) and commits it alongside `data.json`/`changelog.json`/`scrape_log.json` if anything changed.

**Notification:** a dedicated step opens/updates a single de-duplicated GitHub Issue titled "Health check failing" (with current errors/warnings + run link) when `overall == "error"`, and auto-closes it with a resolved comment once healthy again. This is the actual "tell me" channel — GitHub emails repo watchers on issue open/comment by default, which is more reliable than depending on the user's personal Actions-failure-email settings. **Known gap:** if the scraper step itself fails, the status-write step (and this notify step's health signal) gets skipped — see `CODE_REVIEW.md`.

The job only fails (red X) in a dedicated final `if: always()` step, deliberately last, so the status.json commit and the GitHub Issue notification always happen first regardless of health.

### `scrape-teams.yml` — "Refresh Team Rosters" (manual, self-hosted)
Runs `scraper.py --teams-only`. Use after transfer-window roster changes. Split out from the old daily full scrape so a roster refresh doesn't require a ~20 min full run.

### `scrape-rider-profiles.yml` — "Backfill New Rider Profiles" (manual, self-hosted)
Runs `scrape_rider_profiles.py` in its default mode (new/unseen riders only). Use when a rider is missing from search/rankings/rider modals. Winner palmares for riders already in the file are kept current separately via the `uci-winner-profiles` Cowork scheduled task (`--update-winners`).

### `update-data.yml` — "Full Scrape - Calendar & Teams" (manual, self-hosted)
The full `scraper.py` (no flags) — calendar discovery, team rosters, rider-profile backfill, and startlists all together (~20 min). Only needed at season start or when the race calendar itself changes (races added/postponed/cancelled) — everything else has its own focused workflow above. Includes pre- and post-scrape validation (reachability, JSON validity, required keys, race-count sanity, >20% shrink check against the pre-scrape copy).

### `update-co-stats.yml` — "Update CyclingOracle Stats" (scheduled, `ubuntu-latest`)
Runs `scrape_cyclingoracle.py` weekly (Monday 6am UTC) and commits `rider_profiles.json` if `co_stats` coverage changed.

---

## Key Files

| File | Purpose |
|------|---------|
| `data.json` | Race calendar, results, classifications, teams, startlists (~3 MB) |
| `rider_profiles.json` | All rider profiles — photo, bio, specialty scores, `co_stats`, career wins (~4–5 MB) |
| `pcs_stats.json` | PCS statistics tables powering the Stats tab |
| `palmares.json` | Historical winner lists per race, powering the Historical tab (Stats section). Each race has `classifications: {gc, points, kom, youth}` (stage races only have points/kom/youth — one-day races only have `gc`) with year-by-year top-3 podiums including each rider's `nat` flag code. Populate/refresh via `scrape_palmares.py` |
| `best_teams.json` | Team Claudius (AI opponent) squad per race, regenerated after every scrape |
| `changelog.json` | Recent notable changes shown in the app |
| `scrape_log.json` | Per-race probe outcomes from the last `--results-only` run — consumed by `health-check.yml` to detect silent parser drift |
| `status.json` | Machine-readable health snapshot, written by `heal.py` (local) or `health-check.yml` (CI) |
| `index.html` | Entire PWA — HTML + CSS + JS in one file (current APP_VERSION v98) |
| `sw.js` | Service worker — network-first for data files, cache-first for static assets |
| `manifest.json` | PWA manifest — icons, theme colour, install behaviour |
| `push_subscriptions.json` | Browser push subscription endpoints (not in git if not committed) |
| `cycling.db`, `data.js` | A parallel SQLite-backed data pipeline (`import_to_db.py`, `rebuild_cycling_db.py`, `scrape_rider_full.py`) that does **not** appear to be wired into the live `index.html` (no reference to `data.js` found anywhere in it) — looks like an abandoned/experimental migration. See `CODE_REVIEW.md`. |

---

## App Tabs

| Tab | Data source | Notes |
|-----|-------------|-------|
| Live / Upcoming / Recent | `data.json` | Auto-refreshes every 30 min; `silentCheck()` runs on tab visibility too |
| Teams | `data.json` teams section | Rider rows open modal from `rider_profiles.json`; full-peloton search |
| Following | `localStorage` + `rider_profiles.json` | Star riders, see live status and last result |
| Stats | `pcs_stats.json` | Category filter + accordion rows; filters out women's riders by slug |
| Rankings | `rider_profiles.json` | Spec score × quality multiplier; capped at age ≤35, current roster only |
| Fantasy | `localStorage` | No backend — teams stored per-race keyed by slug |
| Help | Static | Inline glossary |

**Rider modal:** lazy-loads `rider_profiles.json` on first open, cached in memory. Shows photo, bio, specialty bars, and career wins for any of the ~1800 profiled riders. Triggered from race results, team rosters, stats tables, rankings, and the Following tab — no external links.

**Fantasy league mechanics:**
- Squad size: `maxSquad(raceKey)` — 8 riders for Grand Tours (`total_stages >= 21`), 7 for other stage races, 3 for one-day races (`total_stages === 1`, i.e. pick the actual podium, not a spread bet)
- Budget: 100 credits; costs scaled `COST_FLOOR=4` to `COST_CEIL=22` via √ of race points
- Points: stage top-10, GC top-10, jersey holders (Points/KOM/Youth, 15 pts — not if rider also leads GC/Yellow)
- Team codes: base64-encoded JSON, imported via `fDoImport()`. **Known bug:** import validation checks a hardcoded 8-rider cap regardless of race type instead of `maxSquad(raceKey)` — see `CODE_REVIEW.md`.
- `Team Claudius` (I Claudius): AI opponent, **one squad per race** (not multiple difficulty tiers), generated by `generate_best_teams.py` from CyclingOracle `co_stats` via an exact 0/1 knapsack, loaded from `best_teams.json`
- Teams stored in `localStorage` under `fantasy_race_teams` keyed by race slug

---

## Push Notifications

Uses the Web Push API with VAPID authentication.

- **VAPID keys:** private key in `scraper.py`, public key in `index.html` — must be a matched pair. Do not regenerate without also clearing all existing browser subscriptions.
- **Subscription flow:** user clicks 🔔 in app → browser subscribes → saves `push_subscriptions.json` locally → user copies to project folder → commit to repo for CI delivery.
- **Triggers:** new stage result, race starting tomorrow.
- **Requires:** `pip install pywebpush` locally. CI installs it automatically.
- **Note:** Chrome routes subscriptions through FCM (`fcm.googleapis.com`). Corporate/restricted networks may block this.

---

## Git Workflow (local + CI conflict avoidance)

CI commits `data.json` at 11am and 5pm UTC. To avoid conflicts on manual pushes:

```bash
# Always pull before committing
git stash && git pull --rebase && git stash pop
py scraper.py --results-only
git add data.json && git commit -m "results: ..." && git push

# If push is still rejected
git pull --rebase && git push
```

---

## Race Filtering

**Men's only:** women's races filtered by UCI category (`1.WWT`, `2.WWT`, `1.W`, `2.W`, `1.1W`, `2.1W`) and by name keywords (women, ladies, femmes, dames). Applied in scraper + CI post-scrape.

**Filter chips in app:** All / Grand Tours / Monuments / UWT ⭐ / Pro Series / 1.1 / 2.1 / This Week. Filter bar hides on Fantasy, Stats, Following, Rankings, and Help tabs.

- Grand Tours: `total_stages >= 21` (consistent across Live, Upcoming, and Recent grouping)
- Monuments: Milano-Sanremo, Ronde van Vlaanderen, Paris-Roubaix, Liège-Bastogne-Liège, Il Lombardia
- `isMonument` and `isGrandTour` flags set as `data-*` attributes on race cards for CSS/filter use

---

## CSS Design Tokens (`:root`)

All colours are CSS custom properties on `:root`. Never use `var(--card)` or `var(--fg)` — these are **not defined** and will render transparent/invisible. Use:

| Variable | Use |
|----------|-----|
| `--bg` | Page background (`#0f1117`) |
| `--surface` | Card / panel background (`#1a1d27`) |
| `--surface2` | Inset / input background (`#22263a`) |
| `--border` | Borders and dividers (`#2e334d`) |
| `--text` | Primary text (`#e8eaf0`) — use instead of `--fg` |
| `--muted` | Secondary / placeholder text (`#8890b0`) |
| `--accent` | Orange highlight (`#f4a261`) |
| `--live` | Red / live indicator (`#e63946`) |
| `--upcoming` | Blue / future (`#4361ee`) |
| `--recent` | Green / past (`#2d6a4f`) |
| `--gold` / `--silver` / `--bronze` | Podium colours |

---

## Key localStorage Keys

| Key | Purpose |
|-----|---------|
| `uci_following` | Array of followed riders `{slug, name, nat}` |
| `fantasy_race_teams` | Object keyed by race slug, each a saved team |
| `fantasy_active_race` | Currently selected race slug |
| `fantasy_league` | Array of imported friend teams |
| `fantasy_watchlist` | Array of watchlisted riders |
| `fantasy_draft` | In-progress team being built |
| `iclaudius_teams` | Object keyed by race slug: Team Claudius entry (one squad per race, loaded from `best_teams.json`) |
| `uci_subscribers_dirty` | Flag: prompt user to re-export subscribers.json |
| `uci_wn_dismissed` | APP_VERSION string when user last dismissed the What's New banner |

---

## Self-Healing Runbook

### data.json is corrupt
```bash
git checkout HEAD -- data.json
```

### Teams out of date (mid-season transfer)
```bash
py scraper.py --teams-only
git add data.json && git commit -m "data: refresh teams" && git push
```

### Rider missing from search
Rider search reads `rider_profiles.json` directly (~1800 riders). If a rider is missing, run:
```bash
py scrape_rider_profiles.py        # picks up any new riders
git add rider_profiles.json && git commit -m "data: rider profiles" && git push
```

### Startlist missing for upcoming race
```bash
py scraper.py --startlists-only
git add data.json && git commit -m "data: startlists" && git push
```

### App shows stale data
1. Hard-refresh: Ctrl+Shift+R
2. Check GitHub Actions — scraper may have failed
3. Trigger manually: GitHub → Actions → Run workflow

### Push notifications not working
- Check `push_subscriptions.json` exists in project folder and is committed
- Check `pywebpush` is installed: `pip install pywebpush`
- Corporate networks may block FCM — test on mobile data
