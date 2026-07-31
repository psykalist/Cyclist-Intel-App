# Changelog

All notable changes to Cyclist Intel App are documented here, newest first.

> **This is the dev/session log.** Claude reads it at the start of every session (ordered to by `CLAUDE.md`) and appends a new entry after every change, before the user pushes.
> Not to be confused with `changelog.json`, which is CI-generated and shown in the app UI.

---

## v130 — 2026-07-30 — Rename the app to "Cyclist Intel App" across code, docs, CI and repo
"I want the Cyclist Intel App to be its name from now on in all areas."

- **Scope.** The user-visible UI was already branded "Cyclist Intel App" (title, header, iOS title, manifest). This pass renames every remaining reference to the old "UCI Calendar" product name — but deliberately **not** the cycling term "UCI" (UCI World Tour, `UCI_CATS`, UCI points = the governing body, not the app).
- **Code / URLs.** `index.html`: download-alert text; `UCI_REPO` → `psykalist/Cyclist-Intel-App`. `sw.js`: header comment, push-notification default title, and cache `uci-calendar-v71` → `cyclist-intel-app-v72` (forces one clean cache refresh). `scraper.py`: both notification-email links → `https://psykalist.github.io/Cyclist-Intel-App` with link text "Cyclist Intel App" (also fixed the wrong `kieransemail.github.io` host → `psykalist`). `scrape_cyclingoracle.py`: User-Agent → `Cyclist-Intel-App-Scraper/1.0`.
- **Docs.** README, ARCHITECTURE, DOCS, CODE_REVIEW, KNOWN_GAPS, CHANGELOG intro, CLAUDE.md — name + `psykalist.github.io/UCI-Calendar` / `github.com/psykalist/UCI-Calendar` → `.../Cyclist-Intel-App`.
- **CI (GitHub Actions).** Commit-author `user.name` `"UCI Calendar Bot"` → `"Cyclist Intel App Bot"` in all 6 workflows.
- **Deliberately left unchanged (data-safety / risk, ~zero branding value):** (1) localStorage keys (`uci_*`, `app-theme`) — the fantasy league & follows are **localStorage-only, no backend/GitHub copy**, so renaming keys would wipe users' saved teams; (2) the Actions concurrency group `uci-calendar-git-write` — the safeguard that serialises CI pushes (a past incident dropped a scraped `data.json` without it); renaming risks it for no visible gain; (3) historical cache-name strings in old `patch_v21*.py` scripts and prior changelog entries. All easy to revisit if wanted.
- **Local folder stays `UCI Calendar & Results`** (can't rename the working dir); CLAUDE.md and memory note this split identity.
- **⚠️ Manual step (you):** rename the GitHub repo to **`Cyclist-Intel-App`** in Settings → the live URL becomes `https://psykalist.github.io/Cyclist-Intel-App/` (old `/UCI-Calendar/` links and already-installed PWAs break until re-added). All in-repo references now point at the new URL.
- Version v129→v130. `index.html` brace balance 0 + `node --check` pass; `scraper.py` / `scrape_cyclingoracle.py` compile; workflow YAML still valid.

## v129 — 2026-07-30 — Scraper: paginate the CyclingFlash calendar (fixes the real Tour de l'Ain gap)
"Why was this tour missing? … please add them."

- **Corrected diagnosis.** v128 blamed a missing *category* (claimed CI only scrapes World Tour / ProSeries / Men Elite and that a 2.1 sits on none of them). That was wrong. CyclingFlash has **no** Europe-Tour/continental calendar filter — **Men Elite is the catch-all** for every men's race, and it was **already a source**. The true cause: the `Men Elite` calendar is **paginated (~12 pages in 2026)** and `discover_races_from_calendar()` only read **page 1**. Tour de l'Ain lives on a later page, so it was never discovered. Its category (2.1) is already in `UCI_CATS`, so nothing else was blocking it.
- **Fix (`scraper.py`).** `discover_races_from_calendar()` now walks every page of each category until the listing ends. Two stop signals, because CyclingFlash differs per category: `Men Elite` returns **HTTP 404** past its last page (empty fetch stops us); `UCI World Tour` / `UCI ProSeries` fit on one page and **repeat that page** for every page number, so we also stop when a page's slug set equals the previous page's. New `MAX_CALENDAR_PAGES = 25` safety cap. Verified against the live site: World Tour 34 (1 page), ProSeries 70 (1 page), Men Elite ~390 unique across 12 pages.
- **Effect & cost.** Discovery jumps from ~96 to ~390 candidate men's slugs. Each candidate still gets one `/race/<slug>` info fetch and is then kept only if its category is in `UCI_CATS` (2.1 / 1.1 / .Pro / .UWT), so the app is **not** flooded with 1.2/2.2 club races — but the run does ~294 extra info-page fetches (~6 min at the 1.2 s delay). Tune via `MAX_CALENDAR_PAGES` if CI time is tight.
- **Slug handoff.** CyclingFlash's slug is `tour-de-lain-2026` (no hyphen before "ain"). Re-keyed the v128 `EXTRA_RACES` fallback to `slug: "tour-de-lain"` / `cf_slug: "tour-de-lain-2026"` so `mergeExtraRaces()` dedupes by slug and CI's richer copy (photos/startlist) wins the moment the paginated scraper runs. Without this the app would have shown the race twice (`tour-de-l-ain` vs `tour-de-lain`).
- Scraper-only logic + one source-side slug fix; `scraper.py` compiles, `index.html` brace balance 0 and main `<script>` passes `node --check`. Version v128→v129.

## v128 — 2026-07-30 — Add Tour de l'Ain 2026 (2.1) via EXTRA_RACES fallback
"Where is the Tour de l'Ain — find it, add it, and get the results."

- **Why it was missing:** ~~only World Tour / ProSeries / Men Elite calendar pages are scraped, and a 2.1 is on none of them.~~ **[Corrected in v129:** this was wrong — Men Elite already covers 2.1 races; the real cause was that only **page 1** of the paginated Men Elite calendar was read, and Tour de l'Ain is on a later page.**]**
- **Fix (same pattern as `EXTRA_TEAMS`/Q36.5):** new `const EXTRA_RACES` holding a full Tour de l'Ain 2026 race object built to the exact `data.json` schema (3 stages with top-10s, `gc_top10`, `points_top10`, `kom_top10`, `youth_top10`, leaders, `last_stage_*`), plus `mergeExtraRaces()` — called right after `mergeExtraTeams()` before any render. Idempotent by slug: if CI ever does pick the race up, the merge skips it (CI wins).
- **Results (28–30 July, Ain, France).** Stage 1 (Parc des Oiseaux→Bourg-en-Bresse) Noah Hobbs; Stage 2 (Saint-Vulbas→Lagnieu) Markel Beloki solo; Stage 3 (Oyonnax→Lélex Monts-Jura) Axel Mariault. **Final GC: 1. Markel Beloki (EF Education-EasyPost), 2. Axel Mariault +0:52, 3. Jamie Meehan +0:55.** Points: Beloki; KOM: Patryk Goszczurny; Youth: Beloki.
- **Data sourcing.** Pulled from procyclingstats via the browser (WebFetch timed out). Rider slugs, ISO nat codes, and teams taken authoritatively from the PCS GC-page DOM (name→slug/nat/team maps) rather than the text extract — the text mis-aligned the team column on same-time rows (e.g. Buck Jones/Bouchard, Gudmestad/Lelandais), which the DOM maps corrected. Display names are derived from PCS slugs (firstname-lastname order, so `shortName()` works), which drops diacritics on a few names (Rémi→Remi) — acceptable for an injected race; a future CI pickup would supersede it.
- Version bumped v127→v128. Brace balance 0; main `<script>` passes `node --check`; `mergeExtraRaces()` verified idempotent and race resolves via `_raceKey` (slug).

## v127 — 2026-07-25 — Exit button uses theme accent; consistent across every panel
"Same colour and on ALL panels depending on dark/light mode — riders list, on the race itself, riders in the following section."

- **Theme-adaptive colour.** `.modal-exit-btn` was a fixed red; now `background: var(--accent); color: var(--bg)`. This tracks the light/dark theme (blue accent on light, warm orange on dark) and stays high-contrast in both: in light mode it's white text (`--bg #ffffff`) on blue; in dark mode it's near-black text (`--bg #0f1117`) on orange.
- **Coverage confirmed for the three contexts named.** The rider profile sheet (`#riderModal`) and the Riders list screen (`#ridersScreen`) are the *only* full-screen popups, and both already carry the Exit button (v126). They are exactly what opens from the **riders list**, from tapping a rider **on a race** (startlist/Riders), and from a card in the **Following** section — so all three now show the same accented Exit button.
- **Smaller dropdown panels made consistent.** The data-health and Update-Scripts dropdown panels keep their corner ✕ (they don't fill the screen), but the ✕ is now accent-coloured, bigger/bolder, with a hover chip — so every closable panel has a visible, theme-matched exit affordance.
- Brace balance 0; main `<script>` passes `node --check`.

## v126 — 2026-07-25 — Visible "✕ Exit" button on full-screen popups
"When there is a popup screen the screens often take up a lot of the screen and it would help if there was a noticeable button to cancel the screen — a button that says exit would be good."

- **Problem:** the two full-height bottom-sheet popups — the rider profile modal (`#riderModal`) and the Riders list screen (`#ridersScreen`) — could only be dismissed by tapping the dark backdrop. On a tall sheet (up to `80vh`) that backdrop is a thin strip, so there was no obvious way to close them; the only affordance was a decorative, non-interactive drag handle.
- **Fix:** added a prominent **`✕ Exit`** button to the static markup of both sheets, calling `closeRiderModal()` / `closeRidersModal()` with no arg (both already short-circuit `if (!e || ...)` to force-close). New `.modal-exit-btn` CSS: solid red (`#e63329`) pill, `position: sticky; top: 0; float: right` so it stays pinned in the top-right corner while the sheet scrolls, above content (`z-index: 6`). Red chosen over `var(--accent)` because the light theme's accent is a pale orange with poor white-text contrast; red also reads universally as close/cancel.
- No JS logic changes — reuses existing close handlers. Brace balance 0; main `<script>` passes `node --check`.

## v125 — 2026-07-24 — Q36.5 riders get ages + photos (CI never scraped them)
"The Team section has no photos and age etc for the riders in Q36.5."

- **Cause:** the same missing-team gap as v123 — the CI rider scrapers (`rider_profiles.json`, `rider_photos.json`) key off `data.json`'s teams, and Q36.5 isn't there, so 7 of the 8 riders had `dob: null`, no `photo`, and weren't in the photo index. The Teams tab showed name + flag but no age and the 🚴 placeholder.
- **Ages:** hardcoded verified birth dates on the `EXTRA_TEAMS` Q36.5 roster (`r.dob`), so the Teams tab and profile modal show "YYYY · NN yrs". Stable facts, cross-checked against Wikipedia/PCS: Pidcock 1999-07-30, Azparren 1999-02-25, Harper 1994-11-23, Hermans 1995-07-29, Howson 1992-08-13, Meurisse 1992-01-31, Van Moer 1998-01-12, Wright 1999-06-13.
- **Photos:** new `EXTRA_PHOTOS` slug→URL map (procyclingstats portraits, verified to load ~160×240), wired as the **last** fallback in the team row, rider modal, and following card — *after* the CI photo index — so a future scraper run that covers Q36.5 automatically wins and this map can be dropped. Pidcock already had a CI photo, so only the other 7 are listed. PCS images use the existing `referrerpolicy=no-referrer` path.
- Brace balance 0; main `<script>` passes `node --check`.

## v124 — 2026-07-24 — Rider flags (full-name nat bug), follow-card team, bib/team sanity check
"When I follow Pidcock he has no flag and is in Astana; we need a sanity check on teams and bibs — if a team is missing (too few bibs) flag it to me, not in the app."

- **No flag on rider profiles — systemic.** `data.json`'s `rider_profiles` store nationality as a full country NAME ("United Kingdom", "Italy") for **250 of 260** riders, and the modal merges that over the correct 2-letter code from `rider_profiles.json`, so `flagcdn.com/.../united kingdom.png` 404s and no flag shows. New `natCode(...cands)` helper + `_NAT_NAMES` map: returns the first candidate that's already an ISO-2 code or maps from a known country name, skipping unmappable values. `flagImg()` now routes through it, and the modal resolves nat as `baseInfo → rider_profiles code → (mapped) data.json name → follow record → race data`. Fixes flags for every affected rider, not just Pidcock.
- **"Astana" on Pidcock's profile** was the modal falling back to PCS `team_history` (which lists him at XDS Astana for 2026) because he had no roster; the v123 Q36.5 injection makes `baseInfo` win, so the modal now shows Q36.5. 
- **Following card:** now awaits `loadRiderProfiles()` before painting (a first visit used to render before the profile cache held the nat, so no flag), resolves nat via `natCode(f.nat, profile.nat, roster nat, race data)`, and picks up the team from the roster (Q36.5 now included) instead of showing nothing/stale.
- **Fixed 4 more bib slug mismatches in `tour_bibs.json`** (surfaced by the new check): `jefferson-cepeda-hernandez→jefferson-albeiro-cepeda`, `nelson-filipe-oliveira→nelson-oliveira`, `ion-izaguirre→ion-izagirre-insausti`, `joel-nicolau→joel-nicolau-beltran`. With Q36.5 (8) + these (4), the reconstructed Tour field is now the full **184** (was 172).
- **New dev-only sanity check `check_teams_bibs.py`** (source, NOT wired into the app UI — reports to the terminal, per the request). Groups the Tour bibs into team blocks, checks each resolves to a `data.json` roster, and distinguishes **MISSING TEAM** (whole block absent from data.json — the Q36.5 failure mode) from **SLUG MISMATCH** (block resolves but a rider is keyed wrong) from **HANDLED** (gap already patched by `EXTRA_TEAMS`). Exits non-zero on an unhandled missing team so it can be wired into CI later. Currently exits 0 (clean).
- Brace balance 0; main `<script>` passes `node --check`; `natCode` unit-checked against the real data values.

## v123 — 2026-07-24 — Add missing Q36.5 team (Pidcock), fix his bib slug
"The team that Tom Pidcock is in is not in the teams and not in the bibs. Use the bibs to create the team and fix Tom's profile."

- **Root cause (two bugs).** (1) Pinarello Q36.5 debuts at the 2026 Tour but the scraper never wrote it to `data.json`'s `teams` array — so its 8 riders (bibs 171–178) had no roster anywhere. `ridersForRace()` reconstructs the field by iterating `appData.teams` and matching bib slugs, so the whole Q36.5 block was silently dropped: no team card, ~12-rider gap in the Tour field, and Pidcock's profile modal had no `baseInfo` → showed no team. (2) `tour_bibs.json` keyed Pidcock as `thomas-pidcock`, but his app roster/profile slug is `tom-pidcock`, so even his own bib wouldn't have resolved once the team existed.
- **Fix 1 — `tour_bibs.json` (source data):** `thomas-pidcock` → `tom-pidcock` (bib 171) so the slug matches the app roster and profile.
- **Fix 2 — `index.html`:** new `EXTRA_TEAMS` (Q36.5 squad rebuilt from the cyclingoo bib block: Pidcock, Azparren, Harper, Hermans, Howson, Meurisse, Van Moer, Fred Wright) + `mergeExtraTeams()`, called right after `data.json` loads and before any render. Idempotent — skipped if the team slug or any rider slug already exists, so it's a no-op the day the scraper starts emitting Q36.5. This restores the Teams-tab card (ProTeam, 👕 placeholder jersey), reconstructs Q36.5 into the live Tour Riders screen with bibs + leader star, and gives Pidcock his team on the profile modal.
- Roster verified against PCS/Domestique 2026 Tour team guide. Brace balance 0; main `<script>` passes `node --check`.

## v122 — 2026-07-23 — Post-race persistence, strike-out abandons, Teams-tab bibs retire, follow-name fix
Batch from "keep the team list with the race post-TDF but drop Teams-tab bibs once it finishes; show riders next to Full Programme for all future races; strike through abandons (Vingegaard, Lipowitz); and Follow shows the maternal surname."

- **Riders lists now persist post-race, for every race (not just the Tour).** CyclingFlash only serves a startlist while a race is *upcoming*, then empties the array once it's live/finished, so a finished race would lose its field. New `cacheStartlist()`/`cachedStartlist()` snapshot each non-empty startlist to `localStorage` (`uci_sl_<slug>`); `ridersForRace()` now resolves in order: live `startlist` → Tour bibs reconstruction → cached snapshot. So the Riders button + inline startlist keep working after any race ends.
- **Teams-tab bibs retire when the Tour finishes.** Added `tourBibsActive()` (true only while the bib race is in `appData.live`). `renderTeamCard` and the `renderRiderRow` fallback now gate all Tour-bib annotations (bib numbers, ⭐ leader star, "N in Tour" badge, bib sort) on it — so once the Tour moves to Recent the Teams tab reverts to a plain roster. **Bibs stay on the per-race Riders screen** (it reads them straight from `tour_bibs.json`, independent of live status).
- **Abandons struck through in the Riders screen + startlist.** `abandonedSlugs(race)` collects slug→status from every stage's `non_finishers` (the v117 data); `startlistTeamsHtml` line-throughs those riders, dims them, and appends the status code (DNF/DNS/OTL…) with a plain-English tooltip. The Riders modal header shows "· N out". Verified against live data: 20 abandons incl. `jonas-vingegaard` (DNF) and `florian-lipowitz` (DNF).
- **Follow a rider no longer shows the maternal surname.** The follow **search results** and **following cards** rendered the raw `name`; both now go through `shortName()` (full name kept as hover title), matching the rest of the app. Stored follow records keep the full name, so notifications/unfollow are unaffected.
- **First-paint:** re-render live *and* recent after `loadTourBibs()` so the reconstructed Riders count and the Teams-tab bib state are correct on load (both ran before bibs previously).
- Brace balance 0; main `<script>` passes `node --check`.

## v121 — 2026-07-23 — Riders screen works for the live Tour (reconstruct field from bibs)
Follow-up to v120: "the Tour de France has not finished, it finishes on Sunday." The v120 Riders button/screen keyed off `race.startlist`, but a **live** Grand Tour has an **empty** startlist array — CyclingFlash drops the startlist page once racing starts (Tour is `status: live`, stage 17/21, `startlist: []`). So the button never appeared on the one race that matters most.

- **New `ridersForRace(race)` source.** Returns the race's own `startlist` when present; otherwise, for the race `tour_bibs.json` covers (`race_slug` match), reconstructs the field from the team rosters — the same slugs+bibs the Teams page already uses. Yields **172 riders** for the live Tour (the 12-rider gap is the known v118 roster-completeness issue), sorted by bib so teams appear with their leader first.
- **Wired everywhere:** the inline **Startlist** toggle, the **👥 Riders (N)** button count, and the modal all now call `ridersForRace()`. Also added `renderStartlist(race)` to the **live/recent multi-stage** branch (previously only upcoming races got an inline startlist) so the Tour has riders "in both places" — inline *and* the separate screen.
- **First-paint fix:** `renderLive` runs before `loadTourBibs()`, so the reconstructed count would be 0 on first paint. Added a `renderLive()` re-render right after bibs load.
- **Bib chips** shown in the startlist/Riders list when known (`.startlist-bib`). Names still go through `shortName()` — e.g. bib 2 "Isaac Del Toro Romero" renders "Isaac Del Toro", maternal surname suppressed.
- Brace balance 0; main `<script>` passes `node --check`.

## v120 — 2026-07-23 — Startlist: suppress maternal surnames again + Riders screen
"The maternal surnames have crept back in… also I want the riders in the tour availed in a separate screen via a button next to the full programme, in both places."

- **Maternal surnames were back in the startlist.** `renderStartlist` rendered `esc(r.name)` — the raw full name — so Hispanic/Lusophone riders showed their maternal (final) surname, unlike everywhere else in the app that already routes names through `shortName()`. Fixed: the per-team markup now goes through a shared `startlistTeamsHtml(sl)` helper that applies `shortName(r.name, r.nat)`, keeps the full name as a hover `title`, and makes each name a clickable `rider-name-link` (startlist entries carry a `slug`) that opens the rider modal.
- **Riders now available in a separate screen too ("both places").** Added a full-screen **Riders** modal (`#ridersScreen`, reusing the rider-modal overlay styling) that lists the same riders grouped by team via the same shared helper — so both the inline **Startlist** toggle and the new screen show identical, surname-suppressed, clickable names.
- **Button beside the Full Programme toggle.** `renderProgramme` now wraps the toggle in a `.programme-toggle-row` and, when the race has a startlist, appends a **👥 Riders (N)** button that calls `openRidersModal(uid)`. Races are registered in a new `_racesByUid` map (populated in `renderRaceCard`) so the modal can look up the startlist by card uid.
- Brace balance verified (diff 0) and the main `<script>` block passes `node --check`.

## 2026-07-19 — Scraper — fix birth-date parsing (was null for 82% of riders)
"Birth dates are inconsistent — some riders show age, some a birth year." Root cause: the DOB parse was silently broken for **1971 of 2404 profiles (82%)**, so most rows fell back to startlist age.

- **Cause:** procyclingstats moved the birth date out of the `borderbox left w65` info block (which the parser scoped to) into a separate `<ul class="list">` where each field is its own `<div>`: `Date of birth:</div><div>23rd</div><div>December</div><div>1998</div>`. Name/nationality/weight still parsed (still in the old block), so profiles looked healthy apart from `dob: null`.
- **Fix:** `parse_rider_page()` now extracts the birth date from the full HTML with a markup-resilient regex (day + month-name + year across separate divs). Tested against the live Kaden Groves page → `1998-12-23`; the older single-div format still falls through to the existing `<li>` parser.
- **Backfill:** added a **`--fix-dob`** mode that re-fetches riders whose stored `dob` is null (skipping CO-only stubs), plus a `mode` input on the *Backfill New Rider Profiles* workflow so it can be triggered from the Actions "Run workflow" dialog. ~1971 riders × 3 pages ≈ 50 min for a one-off run; scheduled runs stay in default mode.
- The Teams page already reads `dob` from the full profile (v119), so once the backfill runs, birth years populate consistently.

## v119 — 2026-07-19 — Rider photos: add referrerpolicy=no-referrer (fixes procyclingstats-hosted ones)
"Some riders have no photo (Kaden Groves had one before)."

- **Cause:** rider photos come from two hosts — cyclingflash's DigitalOcean CDN (~683 riders) and procyclingstats (~206). Confirmed by loading each on the live page: **procyclingstats blocks hotlinking** (fails when a referrer is sent, loads with `no-referrer`); the CDN works either way. None of the rider-photo `<img>` tags set `referrerpolicy`, so the ~206 PCS-hosted photos (Kaden Groves among them — his URL is `procyclingstats.com/images/riders/…kaden-groves-2026.jpg`) silently failed on GitHub Pages.
- **Fix:** added `referrerpolicy="no-referrer"` to every rider-photo `<img>` — Teams roster, rider modal, following card, follow-search results. Verified head-to-head on the live page: PCS images go fail→ok, CDN images stay ok→ok. Also reordered the Teams photo fallback to prefer the curated `rider_photos.json` index over the profile URL.
- **Not fixed here — birth dates.** Only ~26% of roster riders have a DOB *anywhere* (even fully-scraped profiles often lack it — Kaden Groves' profile has `dob: null`), so most rows show age only. This is a `scrape_rider_profiles.py` DOB-parse coverage gap, not an app bug; the Teams page now reads `dob` from the full profile, so it'll reflect any DOB the scraper does capture. Fixing the parse itself is a separate task.

## v118 — 2026-07-19 — Tour bib numbers on the Teams page
Bib (dossard) numbers aren't on CyclingFlash, so a new source was needed — see [source note] below.

- **Source:** cyclingoo.com (`/en/race/tour-de-france-2026/476`, `#bibs` table). Parsed once into a committed **`tour_bibs.json`** (`{ bibs: { slug: bib } }`) — static because bibs don't change mid-race; no scraper added, refresh by re-running when asked. This site is also recorded in memory for future reference.
- **Teams page:** each rider on a Tour team now shows their bib; riders are sorted by bib ascending (lowest first), the lowest bib is flagged as **team leader** (⭐, accent-filled bib), and the team header carries a "🚴 N in Tour de France" badge. `renderRiderRow`/`renderTeamCard` updated; `loadTourBibs()` fetches the file before `renderTeams`.
- **Matching:** cyclingoo slugs mostly match the app roster (157/184 by slug). Added a **hand-verified 15-entry alias map** (into `tour_bibs.json` generation, not runtime) for name/slug variants — critically the ones that are *team leaders* (`juan-ayuso`→`juan-ayuso-pesquera`, `egan-arley-bernal`→…`-gomez`, `richard-antonio-carapaz`→`richard-carapaz`, Higuita, Girmay, Del Toro, Waerenskjold). Without these the ⭐ landed on the wrong rider. Final: **172/184 matched**.
- **Known gap:** the remaining 12 (all 8 of Pinarello Q36.5, plus Izagirre/Cepeda/Nicolau/Oliveira) are absent from the app's team roster entirely, so there's nothing to attach a bib to — a roster-completeness issue for the profile backfill, not a bib one.

Follow-up fixes (same batch), from "no bibs, missing photos, only ages" report:
- **No bibs anywhere = `tour_bibs.json` never shipped.** It was untracked, and `git-push.sh` used `git add -u` (tracked files only), so the new file 404'd live. Hardened `git-push.sh` to also stage brand-new source files (per-glob `git add -A -- '*.py' '*.html' …` loop; GEN_FILES still reset out; `.gitignore` extended with `*_debug.*` so stray debug files aren't caught). One-time: the file must be `git add`ed on this push.
- **Missing photos = a timing bug, not missing data.** `rider_photos.json` covers 100% of the roster, but its index loaded fire-and-forget and the Teams tab often rendered before it arrived (showing only the ~26% of riders with an inlined photo) and never re-rendered. Now exposed as `riderPhotosReady` and awaited before `renderTeams`.
- **Age but no birth date.** Only ~26% of roster riders have a DOB anywhere, and the Teams page only read `r.dob`. `renderRiderRow` now also pulls photo + `dob` from the full rider profile, and teams re-render once `loadRiderProfiles()` finishes in the background — so the profile backfill now actually improves birth dates here.

## 2026-07-19 — Hotfix (scraper) — rider-profile backfill aborted on healthy data
*Backfill New Rider Profiles* failed its own pre-scrape check: `2/5 sample records failed validation — Sam Brand: missing slug, Tomoya Koyama: missing slug`.

- **The data was fine; the validator was wrong.** `rider_profiles.json` holds two legitimate record shapes. A full profile scraped by `scrape_rider_profiles.py` has `slug` + `fetched_at`. A **CyclingOracle-only stub**, written by `scrape_cyclingoracle.py` for a rider with CO stats but no matching procyclingstats profile, is created as `{name, nat, co_stats, _co_only: True, team?}` and by design has neither field — nothing was ever fetched for it.
- `validate_rider()` only knew about shape 1. Stubs are **433 of 2404 records (18%)**, so `pre_scrape_check`'s random 5-record sample was odds-on to hit one and abort the entire run. Intermittent by nature — it would have "passed" on some runs purely by luck.
- **Fix:** `validate_rider()` now branches on `_co_only` and asserts what a stub *is* supposed to carry (non-empty `name` and `co_stats`) rather than what it structurally cannot.
- Verified against the real 2404-record file: **0 failures across the whole file** (not just a sample), and 0 aborts in 2000 simulated random 5-record draws. Previously ~2 in 3 draws would have failed.
- **Related gap, not changed here:** default mode skips any slug already present in `existing`, and a CO-only stub occupies the key — so those 433 riders never get a real profile from a normal run. `--fix-empty` does pick them up (they have no `wins`). Left alone deliberately: the stub keys come from CO slugs and aren't guaranteed to resolve on procyclingstats, so auto-enrolling all 433 risks mass error records.

## v117 — 2026-07-19 — Abandons: riders who stop racing no longer just vanish
Prompted by Jonas Vingegaard abandoning on stage 15 of the Tour today. The app showed nothing at all — he was simply absent from the result, with no indication he'd been in the race and left it.

- **Cause:** `parse_result_rows()` reads the rank cell with `int(rank_text)` and `continue`s on failure. CyclingFlash appends non-finishers to the **bottom of the same result table** with a status code where the rank would be (`<td>DNF</td>`), so every one of those rows was silently discarded. The data was already in the HTML we fetch — we were throwing it away.
- **Scraper:** added `parse_nonfinishers()` + `NONFINISH_CODES` (DNF/DNS/OTL/DSQ/HD/ABD/NR/DF), and `scrape_stage()` now returns a 5th value stored on each stage as `non_finishers`. **No extra HTTP requests** — it parses the page the scraper already downloads. Defensive throughout: rows that don't yield a clean `/profile/` link are skipped, the whole parse is wrapped in try/except returning `[]`, and `MAX_NONFINISHERS = 60` caps a runaway parse (a mass elimination is real; 200 "non-finishers" is a bug).
- **Never downgrades:** an empty re-parse (markup drift) cannot erase a list already held. The key is always written on first pull, which is also what makes the backfill terminate.
- **Backfill:** both stage cache paths now treat a *missing* `non_finishers` key as "re-pull once", so abandons fill in across stages already scraped rather than only appearing on stages raced from now on. The one-day-race path stores them at race level.
- **App:** `renderNonFinishers()` renders a collapsed strip **above** the result table — `⚠ 3 riders out — Vingegaard, Merlier, Van Asbroeck` — which expands to per-rider status badge, flag, tappable name (opens the rider modal), team, and a plain-English explanation of the code, plus a legend.
- **Deliberately does not state a reason.** The source publishes the *status*, not the cause — it says a rider did not finish, never "broken collarbone". The panel explains what DNF/DNS/OTL mean and says outright that the cause isn't recorded, rather than inventing an injury. Checked for a better source first: procyclingstats carries the same codes and no reason, and has no per-race dropouts page (`/gc/dropouts` 404s to the final stage).
- Verified the parser against live markup for TdF stages 13/14/15 — stage 13: 3 DNS, stage 14: 1 DNS + 1 OTL, stage 15: Vingegaard, Merlier, Van Asbroeck all DNF, with teams and flags resolving correctly.

## 2026-07-18 — Rider profile backfill scheduled + coverage health check
Prompted by "Quinn Simmons has no stats". He actually **does** — 9 palmares back to 2021, 9 seasons of team history, 100 career results, photo and specialties, all rendering correctly on the live site. That report was a stale PWA cache. But it exposed a real gap underneath.

**Audit of the 1104-rider roster:** 60% had no palmares, 51% no team history, 54% no season results, 19% no profile at all, 12% no photo.

- **Cause was operational, not technical.** `scrape_rider_profiles.py` already pulls everything wanted (photo, DOB, nationality, height/weight, specialties, `/statistics/wins` career palmares, team history, season results) and is properly incremental — it loads `rider_profiles.json`, skips slugs already present, merges, and commits. But its workflow was `workflow_dispatch` only, so backfill happened only when someone noticed a blank modal.
- **Added a weekly schedule** to *Backfill New Rider Profiles* — Mondays 03:30 UTC, clear of the 6-hourly health checks and 11:00/17:00 results scrapes, still inside the `uci-calendar-git-write` concurrency group. At `DELAY=0.5s` × 3 pages/rider the ~700 outstanding riders take roughly 20–30 min.
- **Added rider-profile coverage to the health check.** `status.json` now carries `rider_roster`, `rider_profiles`, `rider_missing_profile` and `rider_missing_palmares`, and warns above a 15% shortfall. Verified against current data: *"236 of 1104 roster riders (21%) have no profile at all, 755 have no palmares."*
- Note: default mode does **not** retry riders stored with an error or empty result — `--fix-empty` exists for those.

## 2026-07-18 — Scraper — procyclingstats GC fallback
CyclingFlash publishes only a stub GC for some races — verified directly: its Qinghai 2026 GC page contains a single 3-row table with **no times at all**. That's a source limitation, not a parsing bug.

- Added `fetch_pcs_gc()`: pulls GC standings from procyclingstats (reusing the existing `PCS_BASE` / `_pcs_slug()` plumbing) and returns rows in `scrape_classification()` shape.
- **Strictly additive:** only consulted when CF's GC is incomplete, only adopted when PCS returns *more* rows, wrapped in try/except, and the parser returns `[]` on any doubt (no GC table, no rider links, or ranks not a clean 1..n sequence). A PCS markup change degrades to current behaviour rather than corrupting data.
- Parser written against the **real** page markup rather than guesswork: PCS wraps the surname in `<span class="uppercase">`, so "Caicedo Jonathan Klever" → "Jonathan Klever Caicedo" without guessing word order. Nat from `class="flag xx"`, rank-1 keeps elapsed time, others become `+ gap`.
- Result for Qinghai: **3 names with no times → 5 riders with real gaps** (24:23:26, +0:12, +0:15, +0:34, +0:39).
- **Known ceiling:** PCS renders the rest of its GC client-side. Every server-side URL variant (`/gc`, `/gc/result/result`, `?p=results`, `race.php?event=…`) returns the same 5 rows, so 5 is the limit without a headless browser in CI. `gc_source` is recorded on the race when PCS is used.

## v116 — 2026-07-18 — Points/KOM columns were labelled "Time"
The Points and KOM classification tables hold **points**, not times, but `renderTop10()` hard-coded a `Time` header — so the numbers looked like malformed times.

- `renderTop10(rows, valueLabel)` now takes the column label; `renderLeaders()` passes `Pts` for Points and KOM, `Time` for GC and Youth.
- The partial-data note follows suit ("…without points" vs "…without times").

## v115 — 2026-07-18 — Partial results: re-pull them, and say so in the app
Qinghai stage 2 held only 3 riders with no times, and the GC classification only 3 — while Points/KOM had a full 10. It read as a finished result rather than a partial one.

- **Root cause (scraper):** a stage was treated as cached the moment it had *any* `top10` rows, so a result scraped while the source was still publishing froze permanently — it was never re-fetched.
- **Fix:** added `_result_incomplete()` (fewer than `RESULT_EXPECTED_ROWS = 10`, or rows missing times). Incomplete results are re-pulled on later runs until they fill in, and a re-pull that returns *fewer* rows never overwrites what we already hold.
- **App:** result and classification tables now show a plain note — "Partial data — the results source has published N entries… This updates automatically when more is available." — so a short table reads as the source lagging, not an app bug.
- **Health check (pulled vs expected):** `scrape_log.json` now records `expected_rows`, `incomplete_results` and `incomplete_classifications`, plus a top-level `has_incomplete_results`; `health-check.yml` warns with the actual shortfall ("pulled 3 of 10 expected rows").

## v114 — 2026-07-18 — Rider flag no longer disappears when drilling into a rider
The Following list showed a national flag, but opening that rider lost it.

- **Cause:** the Following card reads `f.nat` from the **follow store** (the nat captured in localStorage when you followed the rider), while `openRiderModal()` only looked at `profile.nat` and the team-roster `baseInfo.nat`. When both of those are empty — common for riders not on a loaded team roster, or whose `rider_profiles.json` "Nationality" parse didn't match — the modal rendered no flag at all, so it looked like the flag vanished on drill-down.
- **Fix:** added two more fallbacks — the follow store, then `_natFromRaceData()`, which scans already-loaded result rows, classification tables and startlists for the rider's flag code. Drill-down from race results keeps the flag too, not just from Following.
- Measured against live data: **158** rider slugs that previously resolved to no flag now get one (e.g. `raman-tsishkou → by`, `jonathan-klever-caicedo-cepeda → ec`).

## 2026-07-18 — Hotfix (scraper) — un-raced stages were being marked "cancelled"
Regression from the v111 cancelled-stage detection: **every not-yet-raced stage** on the Tour and Qinghai was flagged cancelled (and counted as done, so the Tour showed "21/21 stages").

- **Cause:** the check keyed off the string `"no result available"`, which CyclingFlash shows on *any* stage page without a result — including stages that simply haven't happened yet. Confirmed against TdF stage 16 (races 21 Jul): it contains "No result available" and no cancellation wording at all.
- **Fix:** only an explicit cancellation sentence counts — `(?:stage|race)\s+(?:was|has been)\s+cancell?ed` (also catches US "canceled"). Verified: Qinghai stage 6 still detected, TdF stage 16 no longer flagged.
- **Self-heal:** removed the "trust the cached cancelled flag" shortcut — a stage with no result is always re-probed — and added a clean-up pass that strips `cancelled` from any stage not positively confirmed this run, including stages beyond the scan break. So the bad flags already written to `data.json` clear themselves on the next scrape, and `stages_completed` returns to the true count.

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
- Renamed the app from "Men's Cyclist Intel App" to **Cyclist Intel App** across the on-screen header, `<title>`, apple/PWA app title, and `manifest.json` (`name` + `short_name`).
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
