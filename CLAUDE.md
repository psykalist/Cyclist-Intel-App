# CLAUDE.md — Project Instructions

> **START OF EVERY SESSION — do this first, before anything else:**
> 1. Read this file (`CLAUDE.md`) in full.
> 2. Read `CHANGELOG.md` (the dev/session log) to see what changed most recently and why.
>
> Follow all rules here before making any changes. **After finishing any change, append an entry to `CHANGELOG.md`** (newest first) before telling the user to push — see Rule 5.

---

## Project

Cyclist Intel App — a single-file PWA (`index.html`) deployed on GitHub Pages. (The local project folder is still named `UCI Calendar & Results`; the GitHub repo is `psykalist/Cyclist-Intel-App`.)
- **Live URL:** https://psykalist.github.io/Cyclist-Intel-App/
- **Project folder:** D:\Claude\Projects\UCI Calendar & Results
- **Bash mount path:** varies per session — the sandbox mounts the folder under `/sessions/<name>/mnt/UCI Calendar & Results/` where `<name>` changes each session. Find it with:
  ```bash
  ls -d /sessions/*/mnt/"UCI Calendar & Results"
  ```
- See `ARCHITECTURE.md` for full system overview.

---

## Workflow Rules (MANDATORY)

### 1. NEVER run git in the sandbox — Claude edits files only, the user pushes

The sandbox reaches the project folder through a FUSE mount that **cannot unlink or
rename files inside `.git/`**. Every git *write* run from the sandbox (`git add`,
`git commit`, `git rebase --continue`) leaves stale `index.lock`/`HEAD.lock` and
cannot complete. The old workaround — a hand-rolled Python plumbing commit — is worse:
it silently corrupted a commit object (wrong header framing) and had to be redone.
The sandbox also has **no push credentials**, so nothing git-writing has to happen there.

**Therefore:**
- Claude ONLY edits working files (Read/Write/Edit). Claude does **not** run
  `git add`, `git commit`, `git rebase`, or any Python git-plumbing in the sandbox.
- After editing, Claude tells the user to run — natively, in Git Bash on Windows:

  ```bash
  bash git-push.sh "vNN: description"
  ```

  That one script does the whole thing on native NTFS (no FUSE): clears stale locks,
  fetches, stages **source only**, commits, rebases onto origin auto-resolving any
  CI-data conflict toward CI, and pushes. If it ever reports a *source* conflict it
  stops and asks for a manual fix; CI-data conflicts never stop it.

**Source vs CI-owned data (the invariant that keeps rebases clean):**
- **You own source:** `index.html`, `*.py`, `*.css`, `manifest.json`, `.github/workflows/*`, docs.
- **CI owns the scraper/heal data files** — `best_teams.json`, `changelog.json`,
  `data.json`, `letour_stages.json`, `palmares.json`, `pcs_enrichment.json`,
  `pcs_stats.json`, `rider_photos.json`, `rider_profiles.json`, `scrape_log.json`,
  `specialty_cache.json`, `status.json`. GitHub Actions rewrites these many times a
  day. **Never hand-edit them and never run the scraper locally.** `git-push.sh`
  keeps them out of local commits and always takes origin's version, so local source
  commits and CI data commits touch disjoint files and cannot conflict. If you add a
  new CI-generated data file, add it to `GEN_FILES` in `git-push.sh`.

> **Removed:** the old "Git plumbing commit" Python workaround. It framed git
> objects with a trailing space instead of a NUL byte, which produced corrupt
> commits. Never reintroduce sandbox-side git writes — use `git-push.sh` natively.

### 2. Bump APP_VERSION on every change

Every bug fix, feature, or tweak must increment `APP_VERSION` in `index.html` before committing.

```js
const APP_VERSION = 'vNN';   // increment NN by 1 each time
```

Check current version first:
```bash
grep "APP_VERSION" /sessions/*/mnt/"UCI Calendar & Results"/index.html
```

### 3. Read and respond to bash output

Always read the output of every bash command and react to errors or unexpected results before continuing.

### 4. Update these instructions when asked

If the user asks to update the workflow, rules, or project instructions, edit this CLAUDE.md file directly and commit it as part of the same version bump.

### 5. Read CHANGELOG.md at session start, and append after every change

`CHANGELOG.md` is the dev/session log — the running record of what changed and *why*.

- **At the start of every session**, read `CHANGELOG.md` (this is also stated at the top of this file).
- **After finishing any change**, add a new entry at the **top** of `CHANGELOG.md` (newest first), matching the existing `## vNN — YYYY-MM-DD — short title` format, with a few bullets covering what changed and why. Do this before telling the user to run `git-push.sh`.
- `CHANGELOG.md` is **source** (you hand-edit it). Do not confuse it with `changelog.json`, which is CI-generated app data — never hand-edit that one.

---

## Coding Rules

- `index.html` is a single-file PWA — all HTML, CSS, and JS lives in one file (~3400+ lines).
- The fantasy league uses `localStorage` only — no backend.
- Squad size: `maxSquad()` returns **8** for Grand Tours (≥21 stages), **7** for other stage races, **3** for one-day races (`total_stages === 1` — pick the actual podium, not a spread bet).
- Budget: **100 credits** per team. `COST_FLOOR = 4`, `COST_CEIL = 22`.
- Points scoring: Stage wins (25pts), GC top-10, jersey holders (15pts each — not if also Yellow).
- `APP_VERSION` is displayed in the app header so the user can confirm which version is live.
- After editing `index.html`, verify JS brace balance:
  ```bash
  python3 -c "
  import glob; h=open(glob.glob('/sessions/*/mnt/UCI Calendar & Results/index.html')[0]).read()
  js=h[h.index('<script>'):h.rindex('</script>')]
  print('Brace diff:', js.count('{') - js.count('}'))
  "
  ```

---

## Key Constants (keep in sync between index.html and generate_best_teams.py)

| Constant | Value |
|----------|-------|
| `FANTASY_BUDGET` | 100 |
| `COST_FLOOR` | 4 |
| `COST_CEIL` | 22 |
| `STAGE_PTS` | 1st=25, 2nd=12, 3rd=8, 4th-10th=3 |
| `GC_PTS` | 1st=50, 2nd=30, 3rd=20, 4th-10th=8 |
| `JERSEY_PTS` | 15 (Points, KOM, Youth — not if rider also leads GC/Yellow) |
| `MAX_SQUAD_GT` | 8 (Grand Tours, ≥21 stages) |
| `MAX_SQUAD` | 7 (other stage races) |
| `MAX_SQUAD_ONEDAY` | 3 (one-day races, `total_stages === 1`) |

---

## I Claudius (AI Opponent)

- Stored per race in `localStorage` under key `iclaudius_teams`
- Generated from `best_teams.json` (built by `generate_best_teams.py`)
- **Single team per race** — one statistically-optimal squad, not multiple difficulty tiers. Riders are scored from CyclingOracle `co_stats` (0-100 scale per attribute; see `scrape_cyclingoracle.py`), not procyclingstats "specialties" (those are unnormalised cumulative career points, NOT 0-100, and are not comparable to co_stats — don't blend them). The squad is chosen by an exact 0/1 knapsack maximising total predicted value under the 100cr budget (`_optimal_team()` in generate_best_teams.py) — a greedy value/cost-ratio pick was tried first but systematically passed over real stars (e.g. Pogačar/Vingegaard cost 20-22cr from real season results, so they lose on ratio to a 4cr unknown) in favour of a bench of nobodies.
- `best_teams.json` schema: `{"races": {"<slug>": {"name", "section", "team": {"riders":[...], "total_cost"}}}}` — note singular `team`, not `teams: {easy, pro, elite}`.
- Appears in the league table with 🏛️ icon and purple AI badge
- Yellow exclusion applies: jersey bonuses don't stack with GC points
- **Scoring is per-race**: `computePoints(riderNames, createdAt, raceKey)` in index.html must always be passed the active race's key. Without it, computePoints sums stage/GC/jersey points across *every* recent+live race regardless of which race a squad was drafted for — so a squad built for an upcoming, not-yet-started race would show bogus nonzero points just because its riders scored well in unrelated past races. This bit us once (Team Claudius "already leading by 261pts" on a race that hadn't started) — always thread raceKey through any new computePoints call site.

---

## Current Version

Check with:
```bash
grep "APP_VERSION" /sessions/*/mnt/"UCI Calendar & Results"/index.html
```
