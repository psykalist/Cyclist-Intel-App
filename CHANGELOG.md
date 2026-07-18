# Changelog

All notable changes to UCI Road Calendar are documented here, newest first.

> **This is the dev/session log.** Claude reads it at the start of every session (ordered to by `CLAUDE.md`) and appends a new entry after every change, before the user pushes.
> Not to be confused with `changelog.json`, which is CI-generated and shown in the app UI.

---

## v113 — 2026-07-18 — Stop result-table rider names wrapping (layout, not name length)
Even already-short two-token names (`Eduardo Sepulveda`, `Emanuel Buchmann` — the latter German, so no surname rule applies) still wrapped. Cause was layout, not naming: `.top10-table` is `table-layout: auto` with no wrap control, so long team names ("Red Bull - BORA - hansgrohe", "Team Visma | Lease a Bike") claimed width and squeezed the rider column until 16–17 character names broke over two lines.

- `.rider-cell { white-space: nowrap }` — the rider name never breaks, at any width.
- `.time-cell` also `nowrap` so gaps stay on one line.
- Added the app's first media query: under 520px the secondary **Team** column (`.team-cell` / `.team-col`) is hidden, giving the name the full row on phones. Team remains visible on desktop.

Two further causes found from a phone screenshot:
- **Empty Team column reserved width.** Classification tables (GC/Points/KOM) carry no team data at all, but the column was still rendered — an empty column squeezing names onto two lines with visibly free space to its right. `renderTop10()` now only renders Team when at least one row actually has one.
- **Stage winners were never shortened.** `renderStages()` rendered `s.winner` raw, bypassing `shortName()` entirely — so `Abner Santiago Umba Lopez` still ran over three lines in the Stage Results list while the same rider was correctly shortened in the tables. Now shortened (→ `Abner Umba`), with the full name kept in the `title` tooltip and nat falling back to the top-10 row.

## v112 — 2026-07-18 — Shorten Hispanic/Lusophone names properly (stop two-line wrapping)
v109 only dropped the maternal surname, which still left three-token names that wrapped — most South/Central American and Spanish riders carry two given names *and* two surnames.

- `shortName()` now also drops the **second given name**: `Jonathan Klever Caicedo Cepeda` → `Jonathan Caicedo`, `Abner Santiago Umba Lopez` → `Abner Umba`, `Egan Arley Bernal Gomez` → `Egan Bernal`, `Harold Alfonso Tejada Canacue` → `Harold Tejada`.
- Handles compound maternal surnames: `Pello Bilbao Lopez de Armentia` → `Pello Bilbao`, guarded on particle index ≥ 3 so `Juan Jose de la Cruz` (where "de la Cruz" *is* the surname) is left whole.
- Particle names still preserved: `Isaac del Toro`, `David De La Cruz`, `Hugo De La Calle`.
- Only applies to the Hispanic/Lusophone nationality set — `van der Poel`, `Geoghegan Hart`, and Asian multi-token names (`Wing Chung Ng`, `Muhammad Nur Aiman Bin Rosli`) are untouched.
- Validated against all 947 rider names in live data: 22 shortened, 0 non-Hispanic names affected.

## v111 — 2026-07-18 — Cancelled stages no longer hide later results; self-correcting stage dates; health check
Reported symptom: Tour of Magnificent Qinghai showed missing recent results and looked finished while still in Live.

Root causes found and fixed:
- **Cancelled stage blocked the pipeline (scraper.py).** The stage loop treated a stage with no result table as "not yet run" and `break`-ed. Qinghai stage 6 was **cancelled (weather)**, so the scraper stopped there and never saw stage 7 (which did run). Fix: detect cancellation ("no result available" / "cancelled"), mark the stage cancelled, count it as decided, and keep probing later stages. Cancelled stages now count toward `stages_completed` so a finished race can retire from Live.
- **Wrong/stale stage dates (scraper.py).** Qinghai stages were cached as 5–12 July (an earlier, pre-reschedule schedule) vs the real 11–18 July, making the race look over with a day left. Added `_derive_stage_dates()` — for one-stage-per-day races it re-derives each stage's date from `start_date`, self-correcting stale dates. Grand tours / rest-day races (window length ≠ stage count, e.g. the Tour) are left untouched. Verified: Qinghai now 11–18 Jul, TdF unchanged.
- **Health check (health-check.yml + scrape_log).** Added an `overdue` signal: if a missing stage's own calendar date has already passed and it isn't cancelled, it's flagged distinctly ("OVERDUE results…") instead of silently stalling or being mislabeled as parser drift. `scrape_log.json` now also records `cancelled_stages` and `has_overdue_stages`.
- **App (index.html).** Cancelled stages render a "✖ Cancelled" label instead of a blank/"Result unavailable" row.

Note: a stale `data.json` I committed during the v109 rebase (16 Jul vs CI's 17 Jul) self-heals on CI's next scrape, which — with the cancelled-stage fix — will also finally pick up Qinghai stage 7.

## v110 — 2026-07-17 — Rebrand to Cyclist Intel App (CIA) + emblem
- Renamed the app from "Men's UCI Road Calendar" to **Cyclist Intel App** across the on-screen header, `<title>`, apple/PWA app title, and `manifest.json` (`name` + `short_name`).
- Added an original inline-SVG emblem after the header name — a circular "agency seal" (compass-star + spoked bike wheel) themed via `--accent`/`--surface2`, so it adapts to light/dark. It scales with the header font (`1.5em`).
- Note: this is an **original** emblem in the intelligence-agency-seal *style*; it is deliberately NOT the actual US CIA seal (official government insignia — can't reproduce / would imply false affiliation).
- Header name now renders every word in the same base text colour, with only the **first letter of each word accented** — C, I, A — so the initials read out as CIA.
- Replaced the UCI rainbow-jersey app icon with a clean **CIA-in-a-circle** icon (orange disc, dark letters, subtle inner ring) — regenerated `favicon.png` (32), `icon-192.png`, and `icon-512.png`.

## 2026-07-17 — Tooling (no app version) — Git workflow overhaul (fixes the recurring FUSE / lock / corruption failures)
- **Root cause 1 — FUSE mechanics:** the sandbox reaches `D:\` via a FUSE mount that can't unlink/rename `.git/` files, so any git write in the sandbox left stale `index.lock`/`HEAD.lock` and couldn't finish. The old Python plumbing-commit workaround was worse — it framed git objects with a trailing space instead of a NUL byte and produced corrupt commits.
- **Root cause 2 — data churn:** GitHub Actions rewrites the scraper JSON many times a day; when a local commit also carried those files, every rebase conflicted, and `git-push.sh` only auto-resolved `data.json`.
- **Fix:** Claude now edits files only and **never runs git in the sandbox** — the user runs `git-push.sh` natively (Git Bash / NTFS, no FUSE). Deleted the plumbing-commit block from `CLAUDE.md` (and stripped 4 stray NUL bytes it had left there). Hardened `git-push.sh` to stage *source only* and auto-resolve *all* CI-owned data files toward origin (`GEN_FILES` list). Fixed stale hardcoded mount paths → session-agnostic globs. Added the "read + append this changelog" rule.
- **Also:** recovered a live `git-push.sh` rebase that had died on 4 CI data files (took origin's newer scrape, preserved v109).
- **Ownership rule:** you own source (`index.html`, `*.py`, `*.css`, `manifest.json`, workflows, docs, this file); CI owns the scraper JSON — never hand-edit those, never scrape locally.

## v109 — 2026-07-17 — Drop maternal surname on results
- Hispanic/Lusophone riders now show a single surname (e.g. `Isaac del Toro Romero` → `Isaac del Toro`) to stop two-line wrapping in the results view.

## v25 — 2026-06-18
- Fix: `normName()` now strips Unicode combining marks (NFD decomposition) so accented names like Pogačar, Möbius etc. correctly match across data sources
- Riders with diacritics no longer fall back to 4cr floor cost

## v24 — 2026-06-18
- Fix: `riderCost()` now normalises input via `normName()` before lookup
- Fix: `buildRiderCosts()` stores all keys as `normName()` so case/punctuation differences never cause misses
- Both fixes together resolve TdF (and all PCS-startlist) riders showing 4cr floor cost

## v23 — 2026-06-18
- Fix: rider costs now reflect season results for PCS-format startlists (e.g. TdF)
- Frontend: `buildRiderCosts` indexes both "Firstname Surname" and "SURNAME Firstname" orderings
- Scraper: normalize PCS startlist names from "SURNAME Firstname" to "Firstname Surname" on scrape

## v22 — 2026-06-18
- Push notification support (bell button in header, VAPID subscription flow)
- Restricted start riders shown on startlist cards
- Scraper: restricted start rider detection from PCS startlist pages
- Service worker cache bumped to `uci-calendar-v22`
- In-app notifications fired when a new stage result is detected on background refresh

## v21c — 2026-06-17
- Race selector rendered as dropdown below instructions panel
- All races selectable (not just live races)

## v21b — 2026-06-17
- Fixed `daysUntil()` rounding bug causing today's races to not appear in Upcoming tab

## v21 — 2026-06-16
- Race-keyed fantasy teams: each race has its own independent team
- No mid-race swaps allowed
- Team codes are race-scoped

## v20 — 2026-06-15
- 9-rider fantasy squads
- Import fix for team codes
- Fixed fModal syntax error

## v19 — 2026-06-14
- Fantasy league MVP: pick riders, score points from stage results
- Export/import team codes for sharing

## v18 — 2026-06-13
- Startlists shown on upcoming race cards (within 21 days)
- Rider profile photos fetched incrementally (50/run)

## v17 — 2026-06-12
- Stage classifications: GC, Points, Mountain, Youth tabs
- Stage result tables with time gaps

## v15 — 2026-06-10
- Fixed rider nationality flags in race result rows (`nat_code` field)
- CyclingFlash as primary data source (replaced PCS scraping)

## v1 — 2026-06-01
- Initial release: live/upcoming/recent race tabs, PWA manifest, service worker
