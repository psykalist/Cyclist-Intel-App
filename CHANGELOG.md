# Changelog

All notable changes to UCI Road Calendar are documented here, newest first.

> **This is the dev/session log.** Claude reads it at the start of every session (ordered to by `CLAUDE.md`) and appends a new entry after every change, before the user pushes.
> Not to be confused with `changelog.json`, which is CI-generated and shown in the app UI.

---

## v110 — 2026-07-17 — Rebrand to Cyclist Intel App (CIA) + emblem
- Renamed the app from "Men's UCI Road Calendar" to **Cyclist Intel App** across the on-screen header, `<title>`, apple/PWA app title, and `manifest.json` (`name` + `short_name`).
- Added an original inline-SVG emblem after the header name — a circular "agency seal" (compass-star + spoked bike wheel) themed via `--accent`/`--surface2`, so it adapts to light/dark. It scales with the header font (`1.5em`).
- Note: this is an **original** emblem in the intelligence-agency-seal *style*; it is deliberately NOT the actual US CIA seal (official government insignia — can't reproduce / would imply false affiliation).

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
