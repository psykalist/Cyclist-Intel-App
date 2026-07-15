"""
scrape_palmares.py — backfill historical winner lists (palmares) for all ~29
races in palmares.json (Grand Tours, Major Tours, Monuments, Championships,
Top Classics).

For each race this fetches the overall/GC podium (top-3) per edition. Stage
races (Grand Tours + Major Tours) additionally fetch the Points, Mountains
(KOM), and Young Rider classification podiums, since those are meaningful
separate competitions in a multi-stage race — one-day races (Monuments,
Championships, Top Classics) only have the one podium. Each rider entry
includes their nationality flag code (`nat`), scraped from PCS alongside
the name.

Must be run locally — PCS blocks CI/cloud IPs, same restriction as
scrape_pcs_stats.py.

Usage:
    py scrape_palmares.py              # fetch races missing from palmares.json
    py scrape_palmares.py --all        # re-fetch every race, overwrite existing
    py scrape_palmares.py --race giro-d-italia   # fetch/refresh one race only
    py scrape_palmares.py --list       # print the race registry and exit

Output: palmares.json (merged in-place — existing races are preserved unless
--all or --race explicitly targets them)
"""

import json
import os
import re
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(BASE_DIR, "palmares.json")
PCS      = "https://www.procyclingstats.com"
DELAY    = 5        # seconds between requests — be polite, same as scrape_pcs_stats.py
TIMEOUT  = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

# ── Race registry ────────────────────────────────────────────────────────────
# slug matches the PCS URL segment: procyclingstats.com/race/{slug}/results/palmares
# category matches palmares.json's category_labels keys.
# "done" races already have full hand-verified history in palmares.json as of
# 2026-07-15 — they're included here so --all / --race can still refresh them.
RACES = [
    # Grand Tours (done — hand-backfilled)
    ("tour-de-france",       "Tour de France",        "grand-tour", 1903),
    ("giro-d-italia",        "Giro d'Italia",          "grand-tour", 1909),
    ("vuelta-a-espana",      "Vuelta a España",        "grand-tour", 1935),
    # Monuments (done — hand-backfilled)
    ("milano-sanremo",       "Milano-Sanremo",         "monument", 1907),
    ("ronde-van-vlaanderen", "Ronde van Vlaanderen",   "monument", 1913),
    ("paris-roubaix",        "Paris-Roubaix",          "monument", 1896),
    ("liege-bastogne-liege", "Liège-Bastogne-Liège",   "monument", 1892),
    ("il-lombardia",         "Il Lombardia",           "monument", 1905),
    # Major Tours (not yet backfilled)
    ("paris-nice",             "Paris-Nice",               "major-tour", 1933),
    ("tirreno-adriatico",      "Tirreno-Adriatico",        "major-tour", 1966),
    ("volta-a-catalunya",      "Volta a Catalunya",        "major-tour", 1911),
    ("itzulia-basque-country", "Itzulia Basque Country",   "major-tour", 1924),
    ("tour-de-romandie",       "Tour de Romandie",         "major-tour", 1947),
    ("tour-de-suisse",         "Tour de Suisse",           "major-tour", 1933),
    ("tour-auvergne-rhone-alpes", "Tour Auvergne-Rhône-Alpes","major-tour", 1982),
    # Championships (not yet backfilled)
    ("world-championship",              "World Championship",    "championship", 1921),
    ("uec-road-european-championships", "European Championship", "championship", 2016),
    # Top Classics (not yet backfilled)
    ("omloop-het-nieuwsblad", "Omloop Het Nieuwsblad", "classic", 1945),
    ("strade-bianche",        "Strade Bianche",         "classic", 2007),
    ("e3-harelbeke",          "E3 Harelbeke",           "classic", 1958),
    ("gent-wevelgem",         "Gent-Wevelgem",          "classic", 1934),
    ("dwars-door-vlaanderen", "Dwars door Vlaanderen",  "classic", 1945),
    ("eschborn-frankfurt",    "Eschborn-Frankfurt",     "classic", 1962),
    ("amstel-gold-race",      "Amstel Gold Race",       "classic", 1966),
    ("la-fleche-wallone",     "La Flèche Wallonne",     "classic", 1936),
    ("san-sebastian",         "San Sebastián Classic",  "classic", 1981),
    ("bretagne-classic",      "Bretagne Classic",       "classic", 1931),
    ("gp-quebec",             "GP Québec",              "classic", 2010),
    ("gp-montreal",           "GP Montréal",            "classic", 2010),
]

DONE_SLUGS = {
    "tour-de-france", "giro-d-italia", "vuelta-a-espana",
    "milano-sanremo", "ronde-van-vlaanderen", "paris-roubaix",
    "liege-bastogne-liege", "il-lombardia",
}

# Stage races have separate Points / Mountains(KOM) / Young Rider
# classifications worth showing alongside the overall GC podium; one-day
# races (Monuments, Championships, Top Classics) only have the one podium.
STAGE_RACE_CATEGORIES = {"grand-tour", "major-tour"}

# PCS's "GC type" filter (procyclingstats.com/race.php?...&gctype=N), found
# on the <select name="gctype"> in the palmares page's filter form. GC (4)
# uses the normal pretty URL; the other three require the numeric race ID
# and the race.php query-string form instead.
GCTYPE = {"points": 5, "kom": 7, "youth": 6}

CATEGORY_LABELS = {
    "grand-tour": "Grand Tours",
    "major-tour": "Major Tours",
    "monument": "Monuments",
    "championship": "Championships",
    "classic": "Top Classics",
}


def strip_tags(s):
    s = re.sub(r'<[^>]+>', ' ', s)
    s = s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>') \
         .replace('&nbsp;', ' ').replace('&#39;', "'").replace('&quot;', '"')
    s = re.sub(r'&#(\d+);',           lambda m: chr(int(m.group(1))),     s)
    s = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), s)
    return re.sub(r'\s+', ' ', s).strip()


def fetch(url):
    for attempt in range(3):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=TIMEOUT) as r:
                data = r.read().decode('utf-8', errors='replace')
            if len(data) < 500:
                raise ValueError(f"Response too short ({len(data)} chars)")
            return data
        except HTTPError as e:
            if e.code == 404:
                return None
            print(f"  HTTP {e.code} (attempt {attempt+1}/3)", flush=True)
            time.sleep(2 ** attempt)
        except (URLError, OSError, ValueError) as e:
            print(f"  Error: {e} (attempt {attempt+1}/3)", flush=True)
            time.sleep(2 ** attempt)
    return None


def _parse_rider_cont(rc):
    """
    Parse one <div class="riderCont">...</div> inner HTML block, e.g.:
        <span class="rnk">1</span><span class="flag mx"></span>
        <a href="rider/isaac-del-toro"><span class="">DEL TORO Isaac</span></a><br/>

    Returns (rank, name, slug, nat) or None if this slot has no rider —
    which legitimately happens for Points/KOM/Young Rider classifications in
    years before PCS tracked that jersey (the <span class="rnk"> is present
    but there's no rider link after it). Earlier versions of this parser
    didn't check for the <a> tag and fell back to stripping tags from the
    whole cell, which for an empty slot returned the leftover rank digit
    ("1") as a fake rider name — fixed here by requiring an actual rider
    link before returning anything.
    """
    rnk_m = re.search(r'<span class="rnk">(\d+)</span>', rc)
    if not rnk_m:
        return None
    rank = int(rnk_m.group(1))

    link_m = re.search(
        r'href=["\'](?:https://www\.procyclingstats\.com)?/?rider/([^"\'/?]+)["\'][^>]*>(.*?)</a>',
        rc, re.DOTALL
    )
    if not link_m:
        return None  # blank podium slot -- no rider recorded

    slug = link_m.group(1).strip('/')
    name = strip_tags(link_m.group(2)).strip()
    if not name:
        return None

    nat_m = re.search(r'<span class="flag ([a-z]{2,3})"', rc)
    nat = nat_m.group(1) if nat_m else ''

    return (rank, name, slug, nat)


def parse_palmares(html, skip_empty=False):
    """
    Parse a PCS palmares page into a list of {year, podium:[{rank,name,slug,nat}]}.

    PCS does NOT use a <table> for this page (an earlier version of this
    parser assumed it did, based on how scrape_pcs_stats.py's other stat
    pages are laid out — that assumption was wrong and silently returned 0
    editions for every race). The real markup, confirmed 2026-07 against a
    saved copy of procyclingstats.com/race/tirreno-adriatico/results/palmares,
    is a plain list:

        <ul class="palmares">
          <li><div class="year">Year</div><div class="riders">...header...</div></li>
          <li>
            <div class="year"><a href="race/{slug}/{YEAR}/gc">{YEAR}</a></div>
            <div class="riders"><div style="...">
              <div class="riderCont"><span class="rnk">1</span><span class="flag xx"></span>
                <a href="rider/{slug}"><span class="">SURNAME Firstname</span></a><br/></div>
              <div class="riderCont"><span class="rnk">2</span>...</div>
              <div class="riderCont"><span class="rnk">3</span>...</div>
            </div></div>
          </li>
          ...
        </ul>

    The very first <li> is a header row ("Year" / "Winner" / "2nd" / "3rd")
    with no digits in its year div — it's skipped naturally because the
    (19|20)\\d{2} year match fails on it.

    skip_empty=True drops editions with a fully empty podium (used for the
    Points/KOM/Young Rider classifications, where many older years genuinely
    have no data — no point storing an empty entry for every one of them).
    """
    editions = []

    ul_m = re.search(r'<ul class="palmares">(.*?)</ul>', html, re.DOTALL)
    if not ul_m:
        return editions
    block = ul_m.group(1)

    for li_m in re.finditer(r'<li>(.*?)</li>', block, re.DOTALL):
        li = li_m.group(1)

        year_div_m = re.search(r'<div class="year">(.*?)</div>', li, re.DOTALL)
        if not year_div_m:
            continue
        year_m = re.search(r'((?:19|20)\d{2})', strip_tags(year_div_m.group(1)))
        if not year_m:
            continue  # header row, or a year cell PCS left blank
        year = int(year_m.group(1))

        podium = []
        for rc_m in re.finditer(r'<div class="riderCont">(.*?)</div>', li, re.DOTALL):
            parsed = _parse_rider_cont(rc_m.group(1))
            if parsed:
                rank, name, slug, nat = parsed
                podium.append({"rank": rank, "name": name, "slug": slug, "nat": nat})

        if skip_empty and not podium:
            continue

        editions.append({"year": year, "podium": podium})

    editions.sort(key=lambda e: e["year"], reverse=True)
    return editions


def load_existing():
    if os.path.exists(OUT_FILE):
        with open(OUT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "generated": "",
        "source": "procyclingstats.com",
        "category_labels": CATEGORY_LABELS,
        "races": {},
    }


def save(data):
    from datetime import date
    data["generated"] = date.today().isoformat()
    tmp = OUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT_FILE)
    print(f"Wrote {OUT_FILE}")


def main():
    args = sys.argv[1:]

    if "--list" in args:
        for slug, name, cat, first in RACES:
            marker = "done" if slug in DONE_SLUGS else "pending"
            print(f"  [{marker:7}] {slug:35} {name:30} ({cat}, since {first})")
        return

    only_race = None
    if "--race" in args:
        only_race = args[args.index("--race") + 1]

    do_all = "--all" in args

    data = load_existing()
    races_out = data.setdefault("races", {})

    targets = RACES
    if only_race:
        targets = [r for r in RACES if r[0] == only_race]
        if not targets:
            print(f"Unknown race slug: {only_race}  (use --list to see all)")
            return

    for slug, name, category, first_edition in targets:
        already_have = slug in races_out and races_out[slug].get("edition_count", 0) > 0
        if already_have and not do_all and not only_race:
            print(f"Skip {slug} (already have {races_out[slug]['edition_count']} editions; use --all or --race to refresh)")
            continue

        url = f"{PCS}/race/{slug}/results/palmares"
        print(f"Fetching {name} ({slug}) — GC ...", flush=True)
        html = fetch(url)
        if html is None:
            print(f"  ✗ Failed to fetch {url}")
            time.sleep(DELAY)
            continue

        gc_editions = parse_palmares(html)
        if not gc_editions:
            print(f"  ✗ No editions parsed — PCS may have changed markup, or this race slug is wrong")
            time.sleep(DELAY)
            continue
        print(f"  ✓ GC: {len(gc_editions)} editions ({gc_editions[-1]['year']}–{gc_editions[0]['year']})")

        is_stage_race = category in STAGE_RACE_CATEGORIES
        classifications = {"gc": gc_editions}

        if is_stage_race:
            race_id_m = re.search(r'name=["\']race["\']\s+value=["\'](\d+)["\']', html)
            race_id = race_id_m.group(1) if race_id_m else None
            if not race_id:
                print(f"  ! Could not find internal race ID — skipping Points/KOM/Young Rider for this race")
                classifications["points"] = classifications["kom"] = classifications["youth"] = []
            else:
                for key, gctype in GCTYPE.items():
                    time.sleep(DELAY)
                    curl = f"{PCS}/race.php?race={race_id}&p=results&s=palmares&gctype={gctype}"
                    print(f"  Fetching {key} ...", flush=True)
                    chtml = fetch(curl)
                    if not chtml:
                        print(f"    ✗ Failed to fetch {key}")
                        classifications[key] = []
                        continue
                    eds = parse_palmares(chtml, skip_empty=True)
                    classifications[key] = eds
                    print(f"    ✓ {key}: {len(eds)} editions with recorded data")

        races_out[slug] = {
            "name": name,
            "category": category,
            "first_edition": first_edition,
            "is_stage_race": is_stage_race,
            "classifications": classifications,
            "edition_count": len(gc_editions),
        }
        save(data)  # save incrementally so partial progress survives a crash
        time.sleep(DELAY)

    print("Done.")


if __name__ == "__main__":
    main()
