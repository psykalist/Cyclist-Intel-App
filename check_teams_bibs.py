#!/usr/bin/env python3
"""
check_teams_bibs.py — offline sanity check for the Tour bib block vs. team rosters.

WHY: the scraper sometimes omits a whole team from data.json's `teams` array
(Pinarello Q36.5 at the 2026 Tour is the case that bit us — see CHANGELOG v123).
When that happens the app can't reconstruct that team's riders from tour_bibs.json,
so a whole squad silently vanishes from the Teams tab and the Tour field, and its
riders (e.g. Pidcock) show no team on their profile.

This is a DEV-ONLY check. It prints a report to the terminal (to you, Kieran) and
exits non-zero if it finds a problem — it does NOT touch the app or the UI. Run it
whenever you want to audit the data, or wire it into CI to get pinged on regressions.

    python3 check_teams_bibs.py

Checks performed:
  1. Every Tour bib maps to a rider that exists in some data.json team roster.
     (A bib whose slug is in no roster = missing team or slug mismatch.)
  2. Each Tour team block (bibs NN1..NN8) has the expected number of riders.
     Too few = a team is partly/entirely missing from data.json.
  3. Reconciles against EXTRA_TEAMS hardcoded in index.html, so a gap the app
     already compensates for is reported as HANDLED, and only NEW gaps are ERRORs.
"""
import json, re, sys, glob, os

HERE = os.path.dirname(os.path.abspath(__file__))

def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)

def extra_team_slugs_from_index():
    """Scrape the rider slugs the app injects via EXTRA_TEAMS in index.html so a
    data.json gap the app already patches isn't reported as a fresh error."""
    try:
        html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    except OSError:
        return set()
    m = re.search(r"const EXTRA_TEAMS\s*=\s*\[(.*?)\];", html, re.S)
    if not m:
        return set()
    return set(re.findall(r"slug:\s*'([a-z0-9-]+)'", m.group(1)))

def main():
    data = load("data.json")
    bibs_doc = load("tour_bibs.json")
    bibs = bibs_doc.get("bibs", {})
    teams = data.get("teams", [])

    # slug -> team name, across every roster in data.json
    roster = {}
    for t in teams:
        for r in t.get("riders", []):
            roster[r.get("slug")] = t.get("name")

    extra = extra_team_slugs_from_index()

    problems = []   # (severity, message)
    handled = []

    # --- Check 1: every bib resolves to a roster slug -------------------------
    unresolved = [(slug, bib) for slug, bib in bibs.items() if slug not in roster]

    # --- Check 2: group bibs into team blocks (bibs NN1..NN8) -----------------
    # Tour numbering: team blocks are 1-8, 11-18, 21-28 ... block = (bib-1)//10
    blocks = {}
    for slug, bib in bibs.items():
        blocks.setdefault((bib - 1) // 10, []).append((bib, slug))

    EXPECTED = 8   # a Tour squad is 8 riders
    print(f"Tour: {bibs_doc.get('race')} {bibs_doc.get('year')} — "
          f"{len(bibs)} bibs across {len(blocks)} team blocks")
    print(f"data.json teams: {len(teams)}   |   EXTRA_TEAMS patches: "
          f"{len(extra)} rider(s)\n")

    for block in sorted(blocks):
        entries = sorted(blocks[block])
        # which data.json team(s) do this block's riders belong to?
        team_names = {roster.get(slug) for _, slug in entries if roster.get(slug)}
        n = len(entries)
        missing = [slug for _, slug in entries if slug not in roster]
        resolved_here = n - len(missing)
        label = " / ".join(sorted(tn for tn in team_names if tn)) or "??? UNKNOWN TEAM"
        flag = ""
        if missing:
            all_handled = all(s in extra for s in missing)
            if all_handled:
                # Every unresolved slug is one the app injects via EXTRA_TEAMS.
                flag = "  [HANDLED by EXTRA_TEAMS]"
                handled.append(label)
            elif resolved_here == 0:
                # No rider in the block is in any roster -> the whole team is
                # absent from data.json. THIS is the "missing team" case.
                flag = "  <<< MISSING TEAM"
                problems.append(("ERROR",
                    f"block {block} (bibs {entries[0][0]}-{entries[-1][0]}) is a "
                    f"MISSING TEAM: none of its {n} riders are in any data.json "
                    f"roster: {[s for _, s in entries]}"))
            else:
                # Block resolves to a present team, but a few slugs don't match
                # the roster -> slug mismatch, not a missing team.
                flag = "  <<< SLUG MISMATCH"
                problems.append(("WARN",
                    f"block {block} ({label}): {len(missing)} bib slug(s) don't "
                    f"match the roster: {missing} — fix the slug in tour_bibs.json"))
        if n < EXPECTED:
            problems.append(("WARN",
                f"block {block} has only {n}/{EXPECTED} bibs — team may be short: {label}"))
            flag += f"  <<< only {n}/{EXPECTED} bibs"
        print(f"  block {block:>2} bibs {entries[0][0]:>3}-{entries[-1][0]:<3} "
              f"n={n} → {label}{flag}")

    # --- Report ---------------------------------------------------------------
    print()
    if unresolved:
        # only the genuinely un-handled ones are errors
        new_unres = [(s, b) for s, b in unresolved if s not in extra]
        if new_unres:
            print(f"UNRESOLVED bibs (slug in no roster, NOT covered by EXTRA_TEAMS): "
                  f"{len(new_unres)}")
            for s, b in sorted(new_unres, key=lambda x: x[1]):
                print(f"   bib {b}: {s}")

    if handled:
        print(f"\nHANDLED (missing from data.json but patched by the app): "
              f"{', '.join(sorted(set(handled)))}")

    errors = [m for sev, m in problems if sev == "ERROR"]
    warns  = [m for sev, m in problems if sev == "WARN"]
    if warns:
        print("\nWARNINGS:")
        for m in warns:
            print("  ! " + m)
    if errors:
        print("\nERRORS (a team is missing from data.json and NOT patched):")
        for m in errors:
            print("  x " + m)
        print("\nACTION: add the missing team to EXTRA_TEAMS in index.html (rebuild "
              "from the bib block) and/or fix the scraper so data.json includes it.")
        sys.exit(1)

    print("\nOK — every Tour bib resolves to a team (directly or via EXTRA_TEAMS).")
    sys.exit(0)

if __name__ == "__main__":
    main()
