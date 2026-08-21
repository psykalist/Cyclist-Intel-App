#!/usr/bin/env python3
"""
fill_stage_descriptions.py — Backfill missing per-stage course DESCRIPTIONS.

WHY THIS EXISTS
---------------
Stage descriptions come from CyclingFlash stage pages, parsed by the scraper's
scrape_stage_details(). But the routine backfill in scraper.py only fetches a
stage when its distance_km is missing ("once a route is captured it is never
re-fetched"). For a race whose route data was captured BEFORE CyclingFlash
published its preview prose — e.g. Vuelta a España 2026, which has distances +
profile images on all 21 stages but 0 descriptions — those descriptions never
get picked up, even though every other Grand Tour has them.

This script re-fetches the stage pages for the targeted race(s) and fills in any
empty description (and opportunistically any other still-missing route field),
WITHOUT clobbering data that's already there. It reuses the exact same
scrape_stage_details() parser, so the text matches the Tour/Giro style exactly.

USAGE
-----
  python fill_stage_descriptions.py                    # Vuelta a España (default)
  python fill_stage_descriptions.py --race giro-ditalia
  python fill_stage_descriptions.py --all              # every race missing descriptions
  python fill_stage_descriptions.py --force            # re-fetch even stages that have a description
  python fill_stage_descriptions.py --dry-run          # report what it would fetch, no writes

Runs on the self-hosted runner / your machine — cyclingflash.com isn't reachable
from GitHub-hosted Actions or the Claude sandbox. After it writes, push with:
  bash git-push.sh "data: fill Vuelta stage descriptions"
"""

import argparse
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data.json"
DEFAULT_RACE = "vuelta-a-espana"

sys.path.insert(0, str(BASE))
from scraper import scrape_stage_details, DELAY  # noqa: E402

# Route fields we're willing to fill when empty. We NEVER overwrite a value that
# already exists (except description when --force) and never touch an existing
# height_profile_img (the result page provides a richer one).
FILLABLE = ("description", "elevation_m", "stage_type", "start_town",
            "finish_town", "distance_km", "start_time", "date_str")


def target_races(data, race_slug, do_all):
    out = []
    for bucket in ("upcoming", "live", "recent"):
        for r in data.get(bucket, []):
            if (r.get("total_stages") or 0) <= 1:
                continue
            if do_all:
                if any(not (s.get("description") or "").strip() for s in r.get("stages", [])):
                    out.append((bucket, r))
            elif r.get("slug") == race_slug:
                out.append((bucket, r))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--race", default=DEFAULT_RACE, help="race slug (default: vuelta-a-espana)")
    ap.add_argument("--all", action="store_true", help="every multi-stage race missing any description")
    ap.add_argument("--force", action="store_true", help="re-fetch even stages that already have a description")
    ap.add_argument("--dry-run", action="store_true", help="report only; no network writes to data.json")
    args = ap.parse_args()

    data = json.loads(DATA.read_text("utf-8"))
    races = target_races(data, args.race, args.all)
    if not races:
        print(f"No matching race found (race={args.race!r}, all={args.all}).")
        return

    total_filled = 0
    for bucket, race in races:
        slug = race.get("cf_slug") or f"{race.get('slug', '')}-{race.get('year', '2026')}"
        year = race.get("year", "")
        stages = race.get("stages") or []
        by_num = {s.get("num"): s for s in stages}
        n_stages = race.get("total_stages") or len(stages)

        targets = [n for n in range(1, n_stages + 1)
                   if args.force or not ((by_num.get(n) or {}).get("description") or "").strip()]
        print(f"\n=== {race.get('name')} [{bucket}]  slug={slug} ===")
        print(f"stages needing a description: {len(targets)} / {n_stages}")

        for n in targets:
            if args.dry_run:
                print(f"  [{n}] would fetch /race/{slug}/stages/stage-{n}")
                continue
            details = scrape_stage_details(slug, n, year=year)
            time.sleep(DELAY)
            if not details:
                print(f"  [{n}] no details returned")
                continue
            stage = by_num.get(n)
            if stage is None:
                stage = {"num": n, "label": f"Stage {n}",
                         "result_url": f"/race/{slug}/result/stage-{n}",
                         "winner": None, "winner_flag": "", "winner_nat": "", "top10": []}
                stages.append(stage); by_num[n] = stage
            wrote = []
            for k in FILLABLE:
                v = details.get(k)
                if v in (None, ""):
                    continue
                # description: fill if empty, or replace under --force
                if k == "description":
                    if (stage.get("description") or "").strip() and not args.force:
                        continue
                # every other field: fill only when target is empty (never clobber)
                elif stage.get(k) not in (None, ""):
                    continue
                stage[k] = v
                wrote.append(k)
            desc_len = len(details.get("description") or "")
            if "description" in wrote:
                total_filled += 1
                print(f"  [{n}] ✓ description ({desc_len} chars)"
                      + (f" + {', '.join(k for k in wrote if k!='description')}" if len(wrote) > 1 else ""))
            else:
                print(f"  [{n}] no description found on page (desc_len={desc_len})")
        race["stages"] = sorted(stages, key=lambda s: s.get("num", 0))

    if args.dry_run:
        print("\n[dry-run] no writes.")
        return
    if total_filled == 0:
        print("\nNothing filled — no writes.")
        return

    try:
        from db_safe import safe_json_write
        safe_json_write(str(DATA), data,
                        required_keys=["live", "upcoming", "recent", "scraped_at"],
                        min_ratio=0.90, label="data.json (stage descriptions)")
    except Exception:
        DATA.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    print(f"\nFilled {total_filled} stage description(s).")
    print('Commit with:  bash git-push.sh "data: fill Vuelta stage descriptions"')


if __name__ == "__main__":
    main()
