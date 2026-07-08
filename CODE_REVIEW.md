# UCI Calendar & Results — Code Review

Full pass over every file in the project (production scripts, all 6 GitHub Actions workflows, `index.html`, and every one-off debug/patch script), done 2026-07-08. Findings below are ordered roughly by severity.

## Critical

### 1. `heal.py` — `check_git_sync()` crashes with `NameError` on every run

```python
def check_git_sync():
    """Warn if local branch is behind origin/main."""
    for lf in [GIT_HEAD_LOCK, GIT_INDEX_LOCK]:
        ...
    # Use rev-list only (no fetch) to avoid creating new lock files
    if r2.returncode == 0:        # <-- r2 is never assigned
        behind = int(r2.stdout.strip() or "0")
        ...
```

The comment says "use rev-list only" but the actual `r2 = run([...])` call that was supposed to follow it is missing. `r2` is referenced without ever being defined, so this function raises `NameError: name 'r2' is not defined` every time it runs. It's called unconditionally from `main()` with no `try/except` around it, and nothing after it in `main()` is wrapped in `try/except` either — so this crash happens *before* `write_status()`, `flush_log()`, `print_summary()`, and (with `--push`) `git_push_status()`. In other words, since this bug shipped, `heal.py` has not been writing `status.json`, has not been writing to `heal.log`, and has not been pushing anything to GitHub — it dies partway through every single run. Check `git log` for commits matching `"heal: status update"` (the message `git_push_status()` uses) — if there aren't any, this confirms the local watchdog has never successfully completed a push. Fix is a one-line addition of the missing `run([...])` call before the `if r2.returncode == 0:` line.

## High

### 2. `health-check.yml` — a scraper failure never reaches the "Notify via GitHub Issue" step correctly

The "Write CI status.json" step sets `id: write_status` and exposes `overall` as a step output, which the notify step reads via `${{ steps.write_status.outputs.overall }}`. But if an earlier step fails — most importantly "Run scraper" (`python scraper.py --results-only`) — GitHub Actions marks the job as failed and skips every subsequent step that isn't `if: always()`. "Write CI status.json" does *not* have `if: always()`, so it never runs, `write_status.outputs.overall` is never set, and the "Notify via GitHub Issue" step (which *does* have `if: always()`) reads an empty `OVERALL` env var, falls through to `else: print("Healthy, no open issue to close")`, and never opens the alert issue. The custom notification channel — which the workflow's own comments describe as "the actual 'tell me' channel... more reliable than relying on the user's personal Actions-failure-email settings" — silently doesn't fire for the exact failure mode (scraper crash) it was built to catch. GitHub's own default failure email is the only thing that fires, and that's the fallback this was explicitly built to not depend on. Fix: give "Write CI status.json" `if: always()`, or wrap the scraper-run step so a scraper crash doesn't hard-fail the job before status gets written.

### 3. `update-co-stats.yml` — missing the concurrency group every other write-workflow has

`scrape.yml`, `health-check.yml`, `scrape-teams.yml`, and `scrape-rider-profiles.yml` all set:

```yaml
concurrency:
  group: uci-calendar-git-write
  cancel-in-progress: false
```

with comments explaining this exists specifically because two workflows racing to push to `main` caused `[rejected] main -> main (fetch first)` followed by a failed rebase retry, losing a freshly-scraped `data.json` (documented incident, 2026-07-02 through 2026-07-05). `update-co-stats.yml` has no `concurrency:` block at all, so it can race with any of the other four and hit the same failure mode. Since it only runs weekly (Monday 6am UTC) plus manual dispatch, the odds of collision are low, but there's no reason to leave this one unprotected — it's a two-line fix.

### 4. `index.html` — `fDoImport()` enforces a flat 8-rider cap instead of the race-specific squad size

```js
// Validate squad size — hard cap 8 riders max
if(raw.riders.length>8){
  alert('❌ This team has '+raw.riders.length+' riders — max allowed is 8. Import rejected.');return;
}
```

`maxSquad()` correctly returns 3 for one-day races, 7 for ordinary stage races, and 8 only for Grand Tours (`total_stages >= 21`) — this is the squad-size rule documented in CLAUDE.md and enforced everywhere else in the fantasy code. `fDoImport()` (used when importing a friend's team code into your league table) never calls `maxSquad()` at all; it just checks against a hardcoded `8`. That means an imported team code for a one-day race or a normal stage race can carry up to 8 riders even though a real squad for that race could only ever have 3 or 7 — giving an imported league entry more scoring roster than the format allows. Fix: pass the active race key into `fDoImport` and compare against `maxSquad(raceKey)` instead of the literal `8`.

## Medium

### 5. The SQLite side of the project (`cycling.db`) has drifted into incompatible schemas across scripts

`db_safe.py` / `import_to_db.py` define and maintain one schema (`riders` table with columns like `photo_url`, `sp_oneday`, `sp_gc`, etc.; tables `races`, `stages`, `stage_results`, `race_results`, `classifications`, `riders`, `rider_wins`, `teams`, `team_riders`, `race_palmares`). `scrape_rider_full.py` is written against a *different* schema entirely — it references a `scrape_queue` table, a `rider_teams` table, a `rider_season_results` table, and `riders` columns (`profile_fetched_at`, `photo`, `dob`, `place_of_birth`, `pcs_rank`, `spec_oneday`, `current_team`, `career_fetched_at`) that don't exist anywhere in `import_to_db.py`'s `SCHEMA`. Running `python scrape_rider_full.py` against the current `cycling.db` would fail immediately with `sqlite3.OperationalError: no such table: scrape_queue`. This script is dead / non-functional as it stands.

Separately: `import_to_db.py` also exports `data.js` ("for the HTML viewer, loads via `<script src='data.js'>`"), and `patch_photos.py` rebuilds that same `data.js` from `cycling.db`. A search of `index.html` turns up no reference to `data.js` anywhere — the live app only ever fetches `data.json`. This whole `cycling.db` → `data.js` pipeline (`import_to_db.py`, `rebuild_cycling_db.py`, `patch_photos.py`, `scrape_rider_full.py`, `scrape_letour.py`'s DB write path) looks like an abandoned parallel architecture that isn't wired into anything the live site actually uses. Worth either finishing the migration, or removing/clearly labeling it so it doesn't get mistaken for load-bearing infrastructure in a future session.

### 6. `check_and_fix.py` and `pre_push_check.py` both assert a constant that no longer exists

Both scripts check:

```python
max_sq = re.search(r"MAX_SQUAD\s*=\s*(\d+)", html)
check("MAX_SQUAD = 9", max_sq and max_sq.group(1) == "9", ...)
```

Current `index.html` has no `MAX_SQUAD` constant at all — squad size has been a per-race `function maxSquad(raceKey)` (returning 3/7/8) since the v21 patch, and the "9" the check wants was already stale then. If either script is run today it will report a false failure ("MAX_SQUAD = 9 — not found"). Low real-world impact since these are manual diagnostic scripts, not part of CI, but worth fixing or deleting so a future run doesn't cause a false alarm.

### 7. Two hardcoded secrets committed to a public repo

- `scrape_cyclingoracle.py`: `API_KEY = 'c81823a3-ea7e-4a48-97ab-aa3372fd1a0b'` for `api.cyclingoracle.com`.
- `scraper.py`: the full VAPID **private** key PEM block (`VAPID_PRIVATE_KEY_PEM`) used for Web Push.

This repo is served publicly via GitHub Pages, so both are visible to anyone who looks at the source. The CyclingOracle key is presumably low-stakes; the VAPID private key is more concerning in principle (it's what lets your server authenticate push messages to subscribed browsers) but the realistic worst case is someone else could send arbitrary push notifications to your subscriber list — not account or data compromise. Worth moving both to GitHub Actions secrets / environment variables at some point, not urgent.

## Low / cosmetic

- **`patch_photos.py`** hardcodes `C:\DataDrive\Documents\Claude\Projects\UCI Calendar & Results\...` — a path from before the project moved to `D:\Claude\Projects\...`. Already-applied one-off script, dead now, but would fail immediately if anyone tried to re-run it.
- **Misleading comments repeated in three files** (`scrape_rider_profiles.py`'s `collect_winner_slugs()`, `import_to_db.py`'s `import_data_json()`): both say `data.json` "stores all races under `d['races']` with a `status` field" and call the actual current schema (top-level `live`/`upcoming`/`recent` lists) "legacy". It's the reverse — `live`/`upcoming`/`recent` is what every other script (including `index.html` itself) actually reads and writes; the unified `races` list appears to be a schema that was planned but never adopted. Functionally harmless (both code paths check both), but worth fixing the comments so a future session doesn't get the schema backwards.
- **`scraper.py`'s `send_notifications()`** (the email-alert path, distinct from the Web Push path) is dead code — never called from anywhere, and `SMTP_USER`/`SMTP_PASS` are blank so it would no-op even if called. Its "tomorrow" date math (`today.replace(day=today.day+1) if today.day<28 else date(year, month+1, 1)`) is wrong for the 28th–31st of any month that isn't exactly 29/30/31 days long relative to that check — e.g. July 28 → jumps to August 1 instead of July 29. Latent only; not currently reachable.
- **`main_results_only()`'s stage-probing loop** (`scraper.py`) only breaks early once it's found at least one completed stage followed by a gap. If a live race hasn't finished its first stage yet, the loop fetches every remaining stage URL on every run instead of stopping after the first miss — wasted requests, not a correctness bug.
- **`scraper_original.py`** (1127 lines) is a full superseded copy of the scraper, still tracked in the main repo tree alongside the current `scraper.py`. Not a bug, but worth moving into a `backups/`-style folder (or deleting) so it doesn't get mistaken for something live in a future review.
- The project folder itself has ~25 one-off `debug_*.py` / `probe_*.py` / `patch_v21*.py` / `fix_*.py` / `repair_*.py` scripts from past incidents, all already applied and now inert (most have a "pattern not found — already fixed?" guard so they safely no-op if re-run). None of these are bugs; flagging only because "review all code" was explicit — nothing here needs action unless you want to prune the folder.

## What's solid

Worth calling out explicitly since it's easy for a review like this to read as all-negative: `db_safe.py`'s `safe_json_write()` (backup → tmp write → round-trip parse → required-key check → size-regression check → atomic replace → read-back verify → restore-on-failure) is a genuinely careful pattern and it's used consistently across every script that writes `data.json` or `rider_profiles.json`. `scraper.py`'s post-write validation in `main_results_only()` (content-count comparison against a `.bak` file rather than raw byte size) correctly fixes the false-positive truncation bug from earlier this week. The `scrape_log.json` / `possible_parser_drift` mechanism in `health-check.yml` is a well-designed way to catch "scraper exited 0 but is silently blind to real results," which is a failure mode that a simple staleness timer can't see. All 6 workflows correctly force `PYTHONUTF8`/`PYTHONIOENCODING` where needed and all have working around the self-hosted runner's PATH/profile quirks. The women's-race filtering has three independent layers (scraper-side category+keyword filter, CI post-scrape strip step, and the category constants themselves) — appropriately defensive for something that's been a recurring issue.
