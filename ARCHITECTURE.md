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

### `scrape.yml` — "Update UCI Race Data" (primary, runs on self-hosted runner)
Twice daily. Runs `scraper.py --results-only` then `scraper.py --startlists-only`, strips any women's races that slipped through, runs `detect_changes.py`, regenerates `best_teams.json` via `generate_best_teams.py`, then commits `data.json` + `changelog.json` + `best_teams.json` (+ `scrape_log.json` if present).

**Schedule:** 11am UTC and 5pm UTC daily (12pm and 6pm BST).

**Reachability check:** before scraping, fetches a real cyclingflash.com race page with a full browser-like header set and requires >500 bytes back — this replaced an earlier check that hit a dead legacy endpoint and always looked "unreachable" regardless of actual site status.

**`scrape_log.json`:** written by `main_results_only()` in `scraper.py` on every run. Records, per live race, whether the next expected stage page fetched OK and whether a results table was found — lets `health-check.yml` distinguish "stage genuinely hasn't finished yet" from "scraper ran, exited 0, and is silently blind to a page that has results" (`possible_parser_drift`, flagged after 2+ consecutive stalls spanning 10+ hours on the same stage).

**Trigger manually:** GitHub → Actions → "Update UCI Race Data" → Run workflow.

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
| `best_teams.json` | Team Claudius (AI opponent) squad per race, regenerated after every scrape |
| `changelog.json` | Recent notable changes shown in the app |
| `scrape_log.json` | Per-race probe outcomes from the last `--results-only` run — consumed by `health-check.yml` to detect silent parser drift |
| `status.json` | Machine-readable health snap