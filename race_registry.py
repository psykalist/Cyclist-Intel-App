#!/usr/bin/env python3
"""
race_registry.py — a self-learning database of the races the app has ever seen.

WHY
---
Bib numbers, start-lists, course details and stage profiles for a race live on
CyclingFlash / procyclingstats / cyclingoo under slugs that repeat every year
(``tour-of-britain-2025`` -> ``tour-of-britain-2026``) and in roughly the same
calendar slot. Nothing in the app remembered a race existed once its year rolled
over, so each edition had to be rediscovered and (for bibs) wired up by hand.
This registry is the memory: every scrape upserts every discovered race into
``race_registry.json`` — name, source slugs, category, this year's dates/stages
— and rolls a "typical" calendar slot forward from the history. A future edition
is therefore already known (slugs + roughly-when) before it is even on the
calendar, which is what lets the automation reach out for its data unprompted.

The registry is DERIVED but additive, and is treated as SOURCE: hand-fixable
overrides (``sources``, ``wants_bibs``) live on each entry and are never
overwritten by the upsert. It is NOT one of git-push.sh's CI-owned GEN_FILES —
a scrape updates it and commits it like any other source change.

USAGE
-----
  python race_registry.py                 # upsert from data.json, write race_registry.json
  python race_registry.py --dry-run       # show what would change, write nothing
  python race_registry.py --data other.json --out other_registry.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data.json"
OUT = BASE / "race_registry.json"

_YEAR_SUFFIX = re.compile(r"-20\d\d$")


def race_key(race: dict) -> str:
    """Year-agnostic key for a race. Prefer the app's own `slug` (already
    year-stripped); otherwise strip a trailing -YYYY from cf_slug."""
    slug = (race.get("slug") or "").strip()
    if slug:
        return _YEAR_SUFFIX.sub("", slug)
    cf = (race.get("cf_slug") or "").strip()
    return _YEAR_SUFFIX.sub("", cf)


def _year_of(race: dict) -> int | None:
    y = race.get("year")
    try:
        return int(y)
    except (TypeError, ValueError):
        pass
    for f in ("start_date", "end_date"):
        v = race.get(f) or ""
        m = re.match(r"(20\d\d)-", v)
        if m:
            return int(m.group(1))
    m = re.search(r"-(20\d\d)$", race.get("cf_slug") or "")
    return int(m.group(1)) if m else None


def _md(iso: str | None) -> str | None:
    """'2026-09-02' -> '09-02'."""
    if not iso or not re.match(r"20\d\d-\d\d-\d\d", iso):
        return None
    return iso[5:10]


def _wants_bibs(category: str, stages: int | None) -> bool:
    """Whether it's worth chasing dossard numbers for this race. Stage races
    (the field wears bibs all week) and WorldTour one-day races qualify; small
    one-day races rarely publish a useful bib list."""
    cat = (category or "").lower()
    if (stages or 0) > 1:
        return True
    return "uwt" in cat or "worldtour" in cat or "world tour" in cat


def _mode_md(mds: list[str]) -> str | None:
    """Most common month-day across seen editions; ties break to the latest."""
    mds = [m for m in mds if m]
    if not mds:
        return None
    counts = Counter(mds)
    top = max(counts.values())
    # among the most-common, take the chronologically latest md
    return sorted([m for m, c in counts.items() if c == top])[-1]


def upsert_from_data(reg: dict, data: dict, seen_iso: str | None = None) -> dict:
    """Fold every race in data.json (live+upcoming+recent) into `reg` in place
    and return it. Pure apart from the `seen_iso` timestamp; safe to unit-test."""
    reg.setdefault("races", {})
    reg["updated_at"] = seen_iso or date.today().isoformat()

    for bucket in ("live", "upcoming", "recent"):
        for race in data.get(bucket, []) or []:
            key = race_key(race)
            if not key:
                continue
            year = _year_of(race)
            e = reg["races"].get(key) or {}

            # Stable identity / source slugs — filled once, then preserved so a
            # hand-tuned pcs_slug or cyclingoo_slug survives future upserts.
            e.setdefault("slug", key)
            e["name"] = race.get("name") or e.get("name") or key
            sources = e.setdefault("sources", {})
            sources.setdefault("cf_slug", key)          # CyclingFlash uses <slug>-<year>
            sources.setdefault("pcs_slug", key)          # PCS startlist/bibs
            sources.setdefault("cyclingoo_slug", None)   # optional; set by hand when known

            # Per-year history.
            years = e.setdefault("years", {})
            if year is not None:
                years[str(year)] = {
                    "start": race.get("start_date"),
                    "end": race.get("end_date"),
                    "stages": race.get("total_stages"),
                    "category": race.get("category"),
                    "cf_slug": race.get("cf_slug") or f"{key}-{year}",
                }
                e["last_seen_year"] = max(int(year), int(e.get("last_seen_year") or year))
                e["first_seen_year"] = min(int(year), int(e.get("first_seen_year") or year))

            # Roll the "typical" calendar slot + shape from the history.
            starts = [_md(y.get("start")) for y in years.values()]
            ends = [_md(y.get("end")) for y in years.values()]
            stage_counts = [y.get("stages") for y in years.values() if y.get("stages")]
            latest = years.get(str(e.get("last_seen_year"))) if e.get("last_seen_year") else None
            e["typical_start_md"] = _mode_md(starts)
            e["typical_end_md"] = _mode_md(ends)
            if stage_counts:
                e["typical_stages"] = Counter(stage_counts).most_common(1)[0][0]
            cat = (latest or {}).get("category") or race.get("category")
            e["category"] = cat
            # wants_bibs: keep a hand-set value if present, else derive.
            if "wants_bibs" not in e:
                e["wants_bibs"] = _wants_bibs(cat, e.get("typical_stages"))

            reg["races"][key] = e

    return reg


def load_registry(path: Path = OUT) -> dict:
    if Path(path).exists():
        try:
            return json.loads(Path(path).read_text("utf-8"))
        except (ValueError, OSError):
            pass
    return {"races": {}}


def save_registry(reg: dict, path: Path = OUT) -> None:
    reg["races"] = dict(sorted(reg["races"].items()))
    Path(path).write_text(json.dumps(reg, ensure_ascii=False, indent=1), "utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text("utf-8"))
    reg = load_registry(Path(args.out))
    before = len(reg.get("races", {}))
    upsert_from_data(reg, data)
    after = len(reg["races"])
    bibs = sum(1 for e in reg["races"].values() if e.get("wants_bibs"))
    print(f"race_registry: {after} races known ({after - before} new this run), "
          f"{bibs} flagged wants_bibs")
    if args.dry_run:
        print("[dry-run] not written")
        return
    save_registry(reg, Path(args.out))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
