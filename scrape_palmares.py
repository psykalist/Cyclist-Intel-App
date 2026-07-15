"""
scrape_palmares.py — backfill historical winner lists (palmares) for the
remaining ~21 races in palmares.json (Major Tours, Championships, Top
Classics). The 8 highest-priority races (3 Grand Tours + 5 Monuments) were
already hand-backfilled with full history and live in palmares.json today —
this script fills in the rest and can also be used to refresh/re-verify any
race, including the priority 8, going forward.

Must be run locally (or on the self-hosted runner) — PCS blocks CI/cloud IPs,
same restriction as scrape_pcs_stats.py.

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


def _rider_link(cell_html):
    """Extract (slug, name) from a cell containing a rider link."""
    m = re.search(
        r'href=["\'](?:https://www\.procyclingstats\.com)?/?rider/([^"\'/?]+)["\'][^>]*>(.*?)</a>',
        cell_html, re.DOTALL
    )
    if m:
        return m.group(1).strip('/'), strip_tags(m.group(2)).strip()
    return '', strip_tags(cell_html).strip()


def parse_palmares(html):
    """
    Parse a PCS palmares page into a list of {year, podium:[{rank,name,slug}]}.

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
            rc = rc_m.group(1)
            rnk_m = re.search(r'<span class="rnk">(\d+)</span>', rc)
            if not rnk_m:
                continue  # shouldn't happen outside the header row, which we already skip
            rank = int(rnk_m.group(1))
            slug, name = _rider_link(rc)
            if name:
                podium.append({"rank": rank, "name": name, "slug": slug})

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
        print(f"Fetching {name} ({slug}) ...", flush=True)
        html = fetch(url)
        if html is None:
            print(f"  ✗ Failed to fetch {url}")
            time.sleep(DELAY)
            continue

        editions = parse_palmares(html)
        if not editions:
            print(f"  ✗ No editions parsed — PCS may have changed table markup, or this race slug is wrong")
            time.sleep(DELAY)
            continue

        races_out[slug] = {
            "name": name,
            "category": category,
            "first_edition": first_edition,
            "editions": editions,
            "edition_count": len(editions),
        }
        print(f"  ✓ {len(editions)} editions ({editions[-1]['year']}–{editions[0]['year']})")
        save(data)  # save incrementally so partial progress survives a crash
        time.sleep(DELAY)

    print("Done.")


if __name__ == "__main__":
    main()
