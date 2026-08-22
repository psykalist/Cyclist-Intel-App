#!/usr/bin/env python3
"""
fetch_stage_profiles_local.py — Download stage height-profile images ONCE and
store them locally, so the app stops hotlinking CyclingFlash's CDN for them.

WHY
---
Every stage's `height_profile_img` is a CyclingFlash CDN url
(cyclingflash.ams3.cdn.digitaloceanspaces.com/.../responsive-images/...webp).
That CDN now blocks hotlinks, so the profile images render as broken icons — the
same failure that hit the rider photos. We can't rewrite height_profile_img to a
local path in data.json, because the scraper overwrites that field with a fresh
CDN url on full scrapes (scraper.py 2070 / 2128). So, like rider_photos.json, we
keep a SEPARATE index the scraper never touches:
    stage_profiles.json  =  { "<cdn-url-as-in-data.json>": "profiles/<name>.<ext>" }
The app resolves height_profile_img through this index and serves the local file.

DOWNLOAD FALLBACKS (per image, until one yields real bytes):
  1. the url as stored in data.json (a responsive-images derivative)
  2. its NON-responsive ORIGINAL (…/<id>/<obj>___heightProfile.webp) — these stay
     public even when the derivative 403s (that's why the rider photos worked)
  3. a FRESH url re-scraped from the live CyclingFlash stage page (repairs stale
     objects — e.g. the Vuelta's old id-32659 placeholders that now 403), and
     that fresh url's original variant too.
Whatever url actually serves the bytes, the local file is mapped under BOTH the
data.json url and the fresh url, so the app finds it however the scraper writes it.

GUARANTEES: never re-downloads an image whose local file exists; never overwrites
/deletes an existing file; aborts before writing if mapped-with-file count drops.

USAGE
-----
  python fetch_stage_profiles_local.py                 # all races (default)
  python fetch_stage_profiles_local.py --bucket upcoming live
  python fetch_stage_profiles_local.py --dry-run
  python fetch_stage_profiles_local.py --limit 20

Runs on the self-hosted runner / your machine. Deploy with a manual commit
(profiles/ + stage_profiles.json are source; data.json untouched):
  git add profiles stage_profiles.json && git commit && git pull --rebase && git push
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE = Path(__file__).parent
DATA = BASE / "data.json"
INDEX = BASE / "stage_profiles.json"
IMG_DIR = BASE / "profiles"
CF = "https://cyclingflash.com"

sys.path.insert(0, str(BASE))
try:
    from scraper import fetch as cf_fetch, _cdn_url  # reuse the proven scraper fetch/parse
except Exception:
    cf_fetch = None
    _cdn_url = None

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
TIMEOUT = 20
DELAY = 0.8

SIGS = [(b"\xff\xd8\xff", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png"),
        (b"GIF87a", ".gif"), (b"GIF89a", ".gif")]


def detect_ext(blob):
    for sig, ext in SIGS:
        if blob.startswith(sig):
            return ext
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return ".webp"
    return None


def original_variant(url):
    """responsive-images derivative -> original public object, or None if not one.
    …/<id>/responsive-images/<obj>___heightProfile_1200_345.webp
      -> …/<id>/<obj>___heightProfile.webp
    """
    if "/responsive-images/" not in url:
        return None
    u = url.replace("/responsive-images/", "/")
    u = re.sub(r"_\d+_\d+(\.\w+)(?:\?.*)?$", r"\1", u)
    return u if u != url else None


def download(url):
    if not url:
        return None
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=TIMEOUT) as r:
            blob = r.read()
    except (HTTPError, URLError, OSError) as e:
        print(f"        ✗ {getattr(e,'code',e)} {url[-48:]}")
        return None
    if len(blob) < 512:
        print(f"        ✗ too small ({len(blob)}B)")
        return None
    ext = detect_ext(blob)
    if not ext:
        print(f"        ✗ not an image {blob[:8]!r}")
        return None
    return blob, ext


def fresh_url_from_page(page_url):
    """Re-scrape a live CyclingFlash stage/race page for its current profile url."""
    if not (cf_fetch and _cdn_url):
        return None
    html = cf_fetch(page_url)
    if not html:
        return None
    return _cdn_url(html, "___heightProfile")


def existing_local(stem):
    for ext in (".webp", ".jpg", ".jpeg", ".png", ".gif"):
        p = IMG_DIR / f"{stem}{ext}"
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def collect(data, buckets):
    """Yield (cdn_url, stem, page_url) for every remote profile image in scope."""
    seen = set()
    for b in buckets:
        for r in data.get(b, []):
            cf = r.get("cf_slug") or f"{r.get('slug','')}-{r.get('year','2026')}"
            for s in r.get("stages", []):
                url = s.get("height_profile_img") or ""
                if url.startswith("http") and url not in seen:
                    seen.add(url)
                    yield url, f"{cf}-stage-{s.get('num')}", f"{CF}/race/{cf}/stages/stage-{s.get('num')}"
            url = r.get("height_profile_img") or ""
            if url.startswith("http") and url not in seen:
                seen.add(url)
                yield url, cf, f"{CF}/race/{cf}"


def try_all(orig_url, page_url):
    """Return (blob, ext, working_url) or None, trying the fallback chain."""
    # 1. url as-is
    got = download(orig_url)
    if got:
        return got[0], got[1], orig_url
    # 2. non-responsive original of the stored url
    ov = original_variant(orig_url)
    if ov:
        got = download(ov)
        if got:
            return got[0], got[1], ov
        time.sleep(DELAY)
    # 3. fresh url from the live page (+ its original variant)
    fresh = fresh_url_from_page(page_url)
    time.sleep(DELAY)
    for cand in [fresh, original_variant(fresh or "")]:
        if cand and cand not in (orig_url, ov):
            got = download(cand)
            if got:
                return got[0], got[1], cand
            time.sleep(DELAY)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", nargs="+", default=["live", "upcoming", "recent"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(DATA.read_text("utf-8"))
    index = json.loads(INDEX.read_text("utf-8")) if INDEX.exists() else {}

    items = list(collect(data, args.bucket))
    mapped_before = sum(1 for u in index if (IMG_DIR / Path(index[u]).name).exists())
    print(f"Height-profile images in scope: {len(items)}")

    todo = []
    for url, stem, page in items:
        if index.get(url) and (IMG_DIR / Path(index[url]).name).exists():
            continue
        lp = existing_local(stem)
        if lp:
            index[url] = f"profiles/{lp.name}"
            continue
        todo.append((url, stem, page))
    if args.limit:
        todo = todo[:args.limit]
    print(f"Need to download: {len(todo)}{' (limited)' if args.limit else ''}\n")

    if not args.dry_run:
        IMG_DIR.mkdir(exist_ok=True)

    got_n = 0
    failed = []
    for i, (url, stem, page) in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {stem}")
        if args.dry_run:
            print(f"      would fetch {url[:80]}")
            continue
        res = try_all(url, page)
        if not res:
            print("      ✗ NO IMAGE (all fallbacks failed)")
            failed.append(stem)
            time.sleep(DELAY)
            continue
        blob, ext, working = res
        out = IMG_DIR / f"{stem}{ext}"
        out.write_bytes(blob)
        got_n += 1
        index[url] = f"profiles/{out.name}"           # key by the data.json url
        if working != url:
            index[working] = f"profiles/{out.name}"    # ...and by the url that served it
            print(f"      ✓ {out.name} ({len(blob)//1024} KB) via {'original' if '/responsive-images/' not in working else 're-scrape'}")
        else:
            print(f"      ✓ {out.name} ({len(blob)//1024} KB)")
        time.sleep(DELAY)

    print(f"\n{'='*60}\nNew this run: {got_n} | files on disk: {out_count(IMG_DIR)} | Failed: {len(failed)} | index size: {len(index)}")
    if failed:
        print("Failed:", ", ".join(failed[:30]) + (" …" if len(failed) > 30 else ""))

    if args.dry_run:
        print("\n[dry-run] no writes.")
        return

    mapped_after = sum(1 for u in index if (IMG_DIR / Path(index[u]).name).exists())
    if mapped_after < mapped_before:
        raise SystemExit(f"ABORT: mapped images would drop {mapped_before} -> {mapped_after}.")

    INDEX.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"\nWrote stage_profiles.json ({len(index)} urls mapped)")
    print('Deploy:  git add profiles stage_profiles.json && '
          'git commit -m "data: store stage profile images locally" && '
          'git pull --rebase origin main && git push origin main')


def out_count(d):
    return len([p for p in d.glob("*") if p.is_file()]) if d.exists() else 0


if __name__ == "__main__":
    main()
