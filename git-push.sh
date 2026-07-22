#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# git-push.sh  –  Safe, native push for the UCI Calendar repo
# Usage:  bash git-push.sh "vNN: commit message"
#
# Runs on the user's Windows machine via Git Bash (native NTFS, NO FUSE mount),
# so unlink/rename of .git lock files works and there is no corruption path.
# This is the ONLY place git write operations happen. The Linux sandbox never
# runs git — it only edits working files.
#
# Design invariant: SOURCE and CI-DATA never mix in a commit.
#   • You own source  (index.html, *.py, *.css, manifest.json, workflows, …)
#   • CI owns the scraper/heal data files (see GEN_FILES). On ANY conflict,
#     CI's version wins, and local edits to those files are discarded — so a
#     local source commit and CI's data commits touch disjoint files and can
#     never rebase-conflict.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
LOG="$REPO/push.log"
MSG="${1:-"chore: update $(date '+%Y-%m-%d %H:%M')"}"
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# Files written by GitHub Actions (auto-scrape / heal / update-data). Never
# hand-edited. NOTE: manifest.json and .claude/* are SOURCE — keep them OUT.
GEN_FILES=(
  best_teams.json
  changelog.json
  data.json
  letour_stages.json
  palmares.json
  pcs_enrichment.json
  pcs_stats.json
  rider_photos.json
  rider_profiles.json
  scrape_log.json
  specialty_cache.json
  status.json
)
is_gen() { printf '%s\n' "${GEN_FILES[@]}" | grep -qxF "$1"; }

cd "$REPO"
echo "" >> "$LOG"
log "━━━━ git-push.sh started ━━━━"

# ── 1. Clear stale locks / interrupted merge-rebase state ─────────────────────
log "Clearing stale lock / rebase state…"
for f in .git/index.lock .git/HEAD.lock .git/refs/heads/main.lock \
         .git/MERGE_HEAD .git/CHERRY_PICK_HEAD .git/REBASE_HEAD; do
  [ -e "$REPO/$f" ] && { rm -f "$REPO/$f" && log "  removed $f" || log "  WARN: could not remove $f — delete it manually"; }
done
if [ -d "$REPO/.git/rebase-merge" ] || [ -d "$REPO/.git/rebase-apply" ]; then
  rm -rf "$REPO/.git/rebase-merge" "$REPO/.git/rebase-apply" && log "  cleared stale rebase dir" \
    || log "  WARN: could not clear rebase dir — delete it manually"
fi

# ── 2. Fetch latest ───────────────────────────────────────────────────────────
log "Fetching origin/main…"
if ! git fetch origin main >> "$LOG" 2>&1; then
  log "❌  fetch failed — check network/credentials in $LOG"; exit 1
fi

# ── 3. Stage source changes only — keep CI-owned data files out of the commit ─
git add -u >> "$LOG" 2>&1 || true
# Also stage brand-NEW source files. `git add -u` only touches already-tracked
# files, so a new file (e.g. tour_bibs.json, a new .py/.yml) was silently left
# uncommitted and 404'd on the live site. `git add` honours .gitignore, and the
# GEN_FILES reset below keeps CI-owned data out regardless.
# One `git add` per glob: a glob that matches nothing (e.g. *.css — all inline)
# makes git error and stage NOTHING, so run each independently with `|| true`.
for pat in '*.py' '*.html' '*.css' '*.js' '*.json' '*.md' '*.yml' '*.yaml' '*.sh'; do
  git add -A -- "$pat" >> "$LOG" 2>&1 || true
done
# unstage + discard any local changes to CI-owned files (CI is the sole writer)
git reset -q HEAD -- "${GEN_FILES[@]}" 2>/dev/null || true
git checkout -q -- "${GEN_FILES[@]}" 2>/dev/null || true

# ── 4. Commit (only if source actually changed) ──────────────────────────────
if git diff --cached --quiet; then
  log "No source changes staged — will just sync + push existing commits"
else
  log "Committing: $MSG"
  git commit -m "$MSG" >> "$LOG" 2>&1
fi

# ── 5. Rebase onto origin/main; auto-resolve any CI-data conflict toward CI ────
log "Rebasing onto origin/main…"
if ! git rebase origin/main >> "$LOG" 2>&1; then
  while [ -d "$REPO/.git/rebase-merge" ] || [ -d "$REPO/.git/rebase-apply" ]; do
    conflicts="$(git diff --name-only --diff-filter=U)"
    if [ -n "$conflicts" ]; then
      unresolved=""
      while IFS= read -r cf; do
        [ -z "$cf" ] && continue
        if is_gen "$cf"; then
          git checkout -q origin/main -- "$cf" && git add "$cf" && log "  auto-resolved $cf (CI wins)"
        else
          unresolved="$unresolved $cf"
        fi
      done <<< "$conflicts"
      if [ -n "$unresolved" ]; then
        log "  ERROR: source conflicts need manual fix:$unresolved"
        log "  Run: git rebase --abort   (then resolve and re-run)"
        exit 1
      fi
    fi
    GIT_EDITOR=true git rebase --continue >> "$LOG" 2>&1 || break
  done
fi

# ── 6. Push ───────────────────────────────────────────────────────────────────
log "Pushing to origin/main…"
if git push origin main >> "$LOG" 2>&1; then
  log "✅  Push successful — HEAD is now $(git rev-parse --short HEAD)"
else
  log "❌  Push failed — check $LOG (if rejected, just re-run this script)"; exit 1
fi
log "━━━━ Done ━━━━"
