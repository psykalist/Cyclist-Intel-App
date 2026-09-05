#!/usr/bin/env python3
"""
fetch_all_bibs.py — registry-driven bib fetcher for EVERY near/live race.

The old fetch_race_bibs.py handled one Grand Tour at a time into tour_bibs.json.
This iterates the race registry, and for every race that is live or starting
soon (and wants bibs), fetches its start-list dossards and writes them into a
multi-race ``race_bibs.json`` keyed by the CyclingFlash slug the app already
carries (`race.cf_slug`, e.g. ``lloyds-tour-of-britain-men-2026``). The app then
shows bibs for any race, not just the one Grand Tour.

It reuses fetch_race_bibs.py's proven fetch/parse/match code (importing it has no
side effects — main() is guarded), so there is one parser to maintain.

SLUG LEARNING
-------------
PCS drops sponsors and the "-men" suffix, so the app's CyclingFlash slug
(``lloyds-tour-of-britain-men``) is not the PCS slug (``tour-of-britain``). We
try a small set of candidate slugs (registry override first, then progressively
stripped forms); the first that returns a plausible start-list is remembered
back into race_registry.json's ``sources.pcs_slug`` so next time is a direct hit.

race_bibs.json is SOURCE (not a CI-owned GEN_FILE): committed by the scrape job.

USAGE
-----
  python fetch_all_bibs.py                 # fetch bibs for all near/live races
  python fetch_all_bibs.py --dry-run       # parse + match + report, write nothing
  python fetch_all_bibs.py --lead-days 30  # widen the pre-race window
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path

from fetch_race_bibs import fetch, parse_pcs, parse_cyclingoo, build_roster, match
import race_registry as reg_mod

BASE = Path(__file__).parent
DATA = BASE / "data.json"
REG = BASE / "race_registry.json"
OUT = BASE / "race_bibs.json"

PCS_BASE = "https://www.procyclingstats.com"
DELAY = 1.2
LEAD_DAYS = 25      # begin chasing bibs when a race starts within this many days
MIN_ROWS = 40       # a plausible men's start-list; fewer => treat as a miss


def strip_year(s: str | None) -> str:
    return re.sub(r"-20\d\d$", "", s or "")


def pcs_slug_candidates(entry: dict, cf_base: str) -> list[str]:
    """Ordered PCS-slug guesses. Registry override wins; then the CF base, the
    base without a trailing '-men', and the base with its leading sponsor token
    dropped (with/without '-men'). Deduped, order preserved."""
    cands = []
    override = ((entry.get("sources") or {}).get("pcs_slug"))
    if override:
        cands.append(override)
    cands.append(cf_base)
    if cf_base.endswith("-men"):
        cands.append(cf_base[:-4])
    parts = cf_base.split("-")
    if len(parts) > 2:                       # drop a leading sponsor word
        cands.append("-".join(parts[1:]))
        if parts[-1] == "men":
            cands.append("-".join(parts[1:-1]))
    out, seen = [], set()
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _year_of(race: dict) -> int | None:
    return reg_mod._year_of(race)


def target_races(data: dict, reg: dict, today: date, lead_days: int) -> list[tuple]:
    """(race, entry, key) for every live race, and every upcoming race that
    both wants bibs and starts within `lead_days`."""
    out = []
    races_reg = reg.get("races", {})
    for bucket in ("live", "upcoming"):
        for race in data.get(bucket, []) or []:
            key = strip_year(race.get("slug") or race.get("cf_slug") or "")
            if not key:
                continue
            entry = races_reg.get(key, {})
            wants = entry.get("wants_bibs", (race.get("total_stages") or 0) > 1)
            if not wants:
                continue
            if bucket == "upcoming":
                sd = race.get("start_date")
                try:
                    if sd and (date.fromisoformat(sd) - today).days > lead_days:
                        continue
                except ValueError:
                    pass
            out.append((race, entry, key))
    return out


def dedupe_rows(rows):
    seen, out = set(), []
    for bib, sl, nm in rows:
        if bib in seen:
            continue
        seen.add(bib)
        out.append((bib, sl, nm))
    return out


def fetch_race_bibs_multi(race, entry, roster, today, lead_days):
    """Try PCS candidate slugs for one race. Returns (payload, winning_slug) or
    (None, None). `roster` is build_roster(data)'s (slugs, namekey, surname)."""
    slugs, namekey, surname = roster
    year = _year_of(race)
    cf_full = race.get("cf_slug") or f"{strip_year(race.get('slug') or '')}-{year}"
    cf_base = strip_year(cf_full)

    for slug in pcs_slug_candidates(entry, cf_base):
        url = f"{PCS_BASE}/race/{slug}/{year}/startlist"
        html = fetch(url)
        time.sleep(DELAY)
        if not html:
            continue
        rows = dedupe_rows(parse_pcs(html))
        if len(rows) < MIN_ROWS:
            continue                              # 404/redirect/empty -> next candidate
        bibs, methods, unmatched = {}, {}, []
        for bib, sl, nm in rows:
            roster_slug, how = match(sl, nm, slugs, namekey, surname)
            methods[how] = methods.get(how, 0) + 1
            if roster_slug:
                bibs[roster_slug] = bib
            else:
                unmatched.append((bib, sl, nm))
        payload = {
            "key": entry.get("slug") or cf_base,
            "race_slug": strip_year(race.get("slug") or cf_base),
            "name": race.get("name") or entry.get("name") or cf_base,
            "year": year,
            "source": url,
            "fetched_at": today.isoformat(),
            "matched": len(bibs),
            "parsed": len(rows),
            "bibs": dict(sorted(bibs.items(), key=lambda kv: kv[1])),
        }
        print(f"  {race.get('name')}: {len(bibs)}/{len(rows)} matched via '{slug}' ({methods})", flush=True)
        if unmatched:
            print(f"    {len(unmatched)} unmatched (add to fetch_race_bibs.ALIASES if roster riders): "
                  + ", ".join(f"{b}:{s}" for b, s, _ in unmatched[:8])
                  + (" ..." if len(unmatched) > 8 else ""), flush=True)
        return payload, slug
    print(f"  {race.get('name')}: no start-list found (tried "
          f"{', '.join(pcs_slug_candidates(entry, cf_base))})", flush=True)
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--lead-days", type=int, default=LEAD_DAYS)
    args = ap.parse_args()

    today = date.today()
    data = json.loads(DATA.read_text("utf-8"))
    reg = reg_mod.load_registry(REG)
    roster = build_roster(data)
    print(f"Roster slugs: {len(roster[0])}")

    out = {"races": {}}
    if OUT.exists():
        try:
            out = json.loads(OUT.read_text("utf-8"))
            out.setdefault("races", {})
        except ValueError:
            out = {"races": {}}

    targets = target_races(data, reg, today, args.lead_days)
    print(f"Targets (live + upcoming within {args.lead_days}d, wants_bibs): {len(targets)}")

    reg_dirty = False
    for race, entry, key in targets:
        payload, slug = fetch_race_bibs_multi(race, entry, roster, today, args.lead_days)
        if not payload:
            continue
        cf_full = race.get("cf_slug") or f"{key}-{_year_of(race)}"
        # Don't overwrite a healthy set with a worse one (e.g. a transient short pull).
        prev = out["races"].get(cf_full)
        if prev and prev.get("matched", 0) > payload["matched"] and payload["matched"] < MIN_ROWS:
            print(f"  keeping previous {cf_full} ({prev.get('matched')} > {payload['matched']})", flush=True)
            continue
        out["races"][cf_full] = payload
        # Learn the slug that worked.
        if slug and (entry.get("sources", {}) or {}).get("pcs_slug") != slug:
            entry.setdefault("sources", {})["pcs_slug"] = slug
            reg.setdefault("races", {})[key] = entry
            reg_dirty = True

    out["generated_at"] = today.isoformat()
    out["races"] = dict(sorted(out["races"].items()))
    total_bibs = sum(len(r.get("bibs", {})) for r in out["races"].values())
    print(f"\nrace_bibs.json: {len(out['races'])} race(s), {total_bibs} bibs total")

    if args.dry_run:
        print("[dry-run] nothing written")
        return
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    print(f"wrote {OUT}")
    if reg_dirty:
        reg_mod.save_registry(reg, REG)
        print(f"updated {REG} (learned PCS slugs)")


if __name__ == "__main__":
    main()
