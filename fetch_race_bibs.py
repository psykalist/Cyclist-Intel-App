#!/usr/bin/env python3
"""
fetch_race_bibs.py — Scrape a race startlist for rider bib (dossard) numbers and
write them into tour_bibs.json, matched to the app's team-roster slugs.

The app shows bibs for whichever race matches tour_bibs.json's `race_slug`
(index.html reads a single bibs file). The Tour is over and the Vuelta is the
live Grand Tour, so this regenerates tour_bibs.json for the Vuelta — no app
change needed.

SOURCES
-------
  --source pcs        procyclingstats startlist (default; predictable url)
  --source cyclingoo  cyclingoo #bibs table  (needs --url, user's preferred)
  --url <URL>         override the startlist url

MATCHING
--------
Startlist rider slugs don't fully line up with the app roster (measured ~85% by
slug; the rest need name/alias fallback — juan-ayuso vs juan-ayuso-pesquera,
egan-bernal vs egan-arley-bernal, soren-warenskjold vs soren-waerenskjold …).
So we match in priority order: exact slug -> alias map -> accent-folded full
name (order-independent) -> surname + first-initial. Unmatched riders are
reported so they can be added to ALIASES.

USAGE
-----
  python fetch_race_bibs.py                         # Vuelta via PCS
  python fetch_race_bibs.py --source cyclingoo --url https://cyclingoo.com/en/race/vuelta-a-espana-2026/<id>
  python fetch_race_bibs.py --dry-run               # parse + match, report, no write

Runs on your machine (PCS/cyclingoo reachable there). Deploy:
  bash git-push.sh "data: Vuelta bib numbers"   (tour_bibs.json is SOURCE, not GEN_FILES)
"""

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE = Path(__file__).parent
DATA = BASE / "data.json"
OUT = BASE / "tour_bibs.json"

RACE_NAME = "Vuelta a España"
RACE_SLUG = "vuelta-a-espana"
YEAR = 2026
PCS_URL = f"https://www.procyclingstats.com/race/{RACE_SLUG}/{YEAR}/startlist"

HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
           "Accept-Language": "en-GB,en;q=0.9"}

# Known source-slug -> roster-slug aliases (extend as unmatched riders surface).
ALIASES = {
    "juan-ayuso": "juan-ayuso-pesquera",
    "egan-bernal": "egan-arley-bernal",
    "soren-warenskjold": "soren-waerenskjold",
    "carlos-rodriguez": "carlos-rodriguez-cano",
    # Vuelta 2026 startlist (PCS slug -> app roster slug), verified by name+team:
    "ivo-emanuel-alves": "ivo-emanuel-oliveira-alves",
    "jorge-arcas": "jorge-arcas-pena",
    "carlos-canal": "carlos-canal-blanco",
    "ivan-romeo": "ivan-romeo-abad",
    "pello-bilbao": "pello-bilbao-lopez-de-armentia",
    "mathias-norsgaard": "mathias-norsgaard-jorgensen",
    "mikel-landa": "mikel-landa-meana",
    "james-shaw": "james-callum-shaw",
    "harold-tejada": "harold-alfonso-tejada-canacue",
    "cristian-rodriguez": "cristian-rodriguez-martin",
    "guillermo-juan-martinez": "guillermo-juan-martinez-huertas",
}


def fetch(url):
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=25) as r:
            return r.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, OSError) as e:
        print(f"fetch failed: {e}")
        return None


def fold(s):
    """Accent-fold + lowercase + collapse to alnum tokens."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()


def parse_pcs(html):
    """[(bib:int, slug, name)] from a PCS startlist. Bib = first number in each
    rider <li>; rider link is /rider/<slug>."""
    out = []
    for li in re.findall(r"<li[^>]*>(.*?)</li>", html, re.DOTALL):
        m = re.search(r'<a[^>]+href="[^"]*rider/([^"/]+)"[^>]*>([^<]+)</a>', li)
        if not m:
            continue
        num = re.search(r"(\d{1,3})", re.sub(r"<[^>]+>", " ", li))
        if not num:
            continue
        out.append((int(num.group(1)), m.group(1).strip(), re.sub(r"\s+", " ", m.group(2)).strip()))
    return out


def parse_cyclingoo(html):
    """[(bib, slug, name)] from a cyclingoo race page #bibs table."""
    out = []
    # rows like: <td>1</td> ... <a href="/en/cyclist/<slug>/<id>">Surname, Firstname</a>
    for m in re.finditer(r'(\d{1,3})\D{0,80}?<a[^>]+href="/en/cyclist/([^"/]+)/\d+"[^>]*>([^<]+)</a>', html, re.DOTALL):
        out.append((int(m.group(1)), m.group(2).strip(), re.sub(r"\s+", " ", m.group(3)).strip()))
    return out


def build_roster(data):
    """roster slug set, folded-namekey -> [slugs], surname -> [slugs]."""
    slugs, namekey, surname = set(), {}, {}
    for team in data.get("teams", []):
        for r in team.get("riders", []):
            sl = r.get("slug")
            if not sl:
                continue
            slugs.add(sl)
            toks = fold(r.get("name", "")) or fold(sl.replace("-", " "))
            namekey.setdefault(" ".join(sorted(toks)), []).append(sl)
            if toks:
                surname.setdefault(toks[-1], []).append(sl)
                surname.setdefault(toks[0], []).append(sl)  # source order varies
    return slugs, namekey, surname


def match(bib_slug, bib_name, slugs, namekey, surname):
    if bib_slug in slugs:
        return bib_slug, "slug"
    if ALIASES.get(bib_slug) in slugs:
        return ALIASES[bib_slug], "alias"
    toks = fold(bib_name) or fold(bib_slug.replace("-", " "))
    key = " ".join(sorted(toks))
    if key in namekey and len(namekey[key]) == 1:
        return namekey[key][0], "name"
    # slug-token key (source name may be "Surname, First"; slug is first-surname)
    skey = " ".join(sorted(fold(bib_slug.replace("-", " "))))
    if skey in namekey and len(namekey[skey]) == 1:
        return namekey[skey][0], "slugname"
    # surname + first-initial disambiguation
    if toks:
        cands = set(surname.get(toks[-1], [])) | set(surname.get(toks[0], []))
        cands = [c for c in cands if c in slugs]
        if len(cands) == 1:
            return cands[0], "surname"
    return None, "unmatched"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["pcs", "cyclingoo"], default="pcs")
    ap.add_argument("--url", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    url = args.url or (PCS_URL if args.source == "pcs" else None)
    if not url:
        sys.exit("cyclingoo needs --url (the race page, e.g. .../en/race/vuelta-a-espana-2026/<id>)")

    html = fetch(url)
    if not html:
        sys.exit("could not fetch startlist")
    rows = parse_pcs(html) if args.source == "pcs" else parse_cyclingoo(html)
    # dedupe by bib, keep first
    seen, rows2 = set(), []
    for bib, sl, nm in rows:
        if bib in seen:
            continue
        seen.add(bib)
        rows2.append((bib, sl, nm))
    rows = rows2
    print(f"Parsed {len(rows)} riders from {args.source}: {url}")
    if len(rows) < 50:
        print("⚠ Suspiciously few riders parsed — the source HTML structure may have changed. "
              "Paste this output so the parser can be adjusted.")

    data = json.loads(DATA.read_text("utf-8"))
    slugs, namekey, surname = build_roster(data)
    print(f"Roster slugs: {len(slugs)}")

    bibs, unmatched, methods = {}, [], {}
    for bib, sl, nm in rows:
        roster_slug, how = match(sl, nm, slugs, namekey, surname)
        methods[how] = methods.get(how, 0) + 1
        if roster_slug:
            bibs[roster_slug] = bib
        else:
            unmatched.append((bib, sl, nm))

    print(f"Matched {len(bibs)}/{len(rows)}  ({methods})")
    if unmatched:
        print(f"\nUNMATCHED ({len(unmatched)}) — add to ALIASES if they belong to a roster rider:")
        for bib, sl, nm in unmatched:
            print(f"  {bib:>3}  {sl:<34} {nm}")

    if args.dry_run:
        print("\n[dry-run] no write.")
        return

    payload = {
        "race": RACE_NAME, "race_slug": RACE_SLUG, "year": YEAR,
        "source": url,
        "updated_at": date.today().isoformat(),
        "note": ("Rider slug -> bib (dossard). Lowest bib in a team = leader. "
                 "Keyed to app roster slugs (alias/name fallback for source variants)."),
        "bibs": dict(sorted(bibs.items(), key=lambda kv: kv[1])),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    print(f"\nWrote tour_bibs.json ({len(bibs)} bibs, race_slug={RACE_SLUG})")
    print('Deploy:  bash git-push.sh "data: Vuelta bib numbers"')


if __name__ == "__main__":
    main()
