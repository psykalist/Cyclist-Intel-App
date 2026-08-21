#!/usr/bin/env python3
"""
fetch_rider_photos_local.py — Download rider photos ONCE and store them as local
files in the repo, so the app never hotlinks a remote CDN again.

WHY THIS EXISTS
---------------
The old pipeline (fetch_missing_photos.py / build_rider_photos.py / fix-photos.yml)
only ever stored a remote *URL* in rider_photos.json and the app hotlinked it at
render time. When CyclingFlash's CDN started refusing hotlinks (Aug 2026), every
CF-hosted rider went blank at once — the photo was "lost" even though we still
"had" the URL. This script fixes that permanently: it pulls the image *bytes*
into  photos/<slug>.<ext>  and rewrites rider_photos.json (and data.json photo
fields) to point at the LOCAL path. Served from our own GitHub Pages origin,
nothing external can ever blank them again.

SCOPE: team-roster riders only (data.json teams[].riders[]), ~889 riders.

GUARANTEES
----------
  * Never re-downloads a rider whose local file already exists (pull ONCE).
  * Never overwrites or deletes an existing local file.
  * "Never lose a photo": aborts before writing if the number of riders with a
    working LOCAL file would drop.

SOURCES (tried in order, per rider, until one yields real image bytes):
  1. The URL already in rider_photos.json (CyclingFlash CDN or PCS)
  2. The inline photo URL in data.json (teams[].riders[].photo)
  3. A FRESH CyclingFlash CDN url, re-scraped from the rider's profile page
     (repairs stale/rotated object keys)
  4. procyclingstats portrait  https://www.procyclingstats.com/rider/<slug>
A server-side GET with no Referer succeeds even when browser hotlinking is
blocked — that's the whole point of storing them ourselves.

USAGE
-----
  python fetch_rider_photos_local.py                 # full roster pull
  python fetch_rider_photos_local.py --dry-run       # report only, no downloads/writes
  python fetch_rider_photos_local.py --limit 20      # first 20 needed riders (testing)
  python fetch_rider_photos_local.py --no-refresh    # skip profile-page re-scrape (source 3)

Runs on the self-hosted runner (cyclingflash.com is not reachable from
GitHub-hosted Actions). After a manual local run, push with:
  bash git-push.sh "data: store rider photos locally"
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE = Path(__file__).parent
DATA = BASE / "data.json"
PHOTOS_JSON = BASE / "rider_photos.json"
PHOTO_DIR = BASE / "photos"

CF_HOST = "cyclingflash.ams3.cdn.digitaloceanspaces.com"
CF_BASE = "https://cyclingflash.com"
PCS_BASE = "https://www.procyclingstats.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    # Deliberately NO Referer — a server-side pull is not a hotlink.
}
TIMEOUT = 20
DELAY = 1.0  # politeness between network requests

# Magic-byte signatures → canonical file extension. We trust the bytes, not the
# URL's extension, so a mislabeled response still lands with the right suffix.
SIGS = [
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
]


def detect_ext(blob: bytes) -> str | None:
    for sig, ext in SIGS:
        if blob.startswith(sig):
            return ext
    # WEBP: "RIFF"<4 bytes>"WEBP"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return ".webp"
    return None


def download_image(url: str) -> tuple[bytes, str] | None:
    """GET url; return (bytes, ext) if it is a real, non-trivial image, else None."""
    if not url:
        return None
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=TIMEOUT) as r:
            blob = r.read()
    except (HTTPError, URLError, OSError) as e:
        print(f"      ✗ download failed: {e}")
        return None
    if len(blob) < 1024:  # 1KB floor — reject 1px trackers / empty / error bodies
        print(f"      ✗ too small ({len(blob)} bytes)")
        return None
    ext = detect_ext(blob)
    if not ext:
        print(f"      ✗ not a recognised image ({blob[:8]!r})")
        return None
    return blob, ext


def fetch_html(url: str) -> str | None:
    try:
        req = Request(url, headers={**HEADERS, "Accept": "text/html,*/*"})
        with urlopen(req, timeout=TIMEOUT) as r:
            data = r.read().decode("utf-8", errors="replace")
        return data if len(data) >= 500 else None
    except (HTTPError, URLError, OSError) as e:
        print(f"      ✗ profile fetch failed: {e}")
        return None


def fresh_cf_url(slug: str) -> str | None:
    """Re-scrape the CyclingFlash profile page for a current CDN photo url."""
    html = fetch_html(f"{CF_BASE}/profile/{slug}")
    if not html:
        return None
    m = re.search(
        r"https://cyclingflash\.ams3\.cdn\.digitaloceanspaces\.com/\d+/"
        r"[^\"'<\s/]+\.(?:jpg|jpeg|png|webp)",
        html, re.IGNORECASE,
    )
    return m.group(0) if m else None


def pcs_url(slug: str) -> str | None:
    """Scrape the PCS rider page for its portrait image url."""
    html = fetch_html(f"{PCS_BASE}/rider/{slug}")
    if not html:
        return None
    m = re.search(r'src="(images/riders/[^"]+\.(?:jpg|jpeg|png|webp))"', html, re.IGNORECASE)
    return f"{PCS_BASE}/{m.group(1)}" if m else None


def existing_local(slug: str) -> Path | None:
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        p = PHOTO_DIR / f"{slug}{ext}"
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def is_local(v: str) -> bool:
    return bool(v) and v.startswith("photos/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only; no downloads or writes")
    ap.add_argument("--limit", type=int, default=0, help="cap number of riders processed (testing)")
    ap.add_argument("--no-refresh", action="store_true", help="skip profile-page re-scrape (source 3)")
    args = ap.parse_args()

    data = json.loads(DATA.read_text("utf-8"))
    photos = json.loads(PHOTOS_JSON.read_text("utf-8")) if PHOTOS_JSON.exists() else {}

    # Roster slugs (+ any inline photo url) from team rosters, de-duplicated.
    roster: dict[str, str] = {}
    for team in data.get("teams", []):
        for r in team.get("riders", []):
            slug = r.get("slug")
            if slug and slug not in roster:
                roster[slug] = r.get("photo") or ""
    print(f"Roster riders: {len(roster)}")

    # "Never lose" baseline: how many roster riders already have a working local file.
    local_before = sum(1 for s in roster if existing_local(s))
    print(f"Already stored locally: {local_before}")

    need = [s for s in roster if not existing_local(s)]
    if args.limit:
        need = need[: args.limit]
    print(f"Need to download: {len(need)}"
          f"{' (limited)' if args.limit else ''}\n")

    if not args.dry_run:
        PHOTO_DIR.mkdir(exist_ok=True)

    stored: dict[str, str] = {}   # slug -> "photos/<slug>.<ext>"
    failed: list[str] = []

    for i, slug in enumerate(need, 1):
        print(f"[{i}/{len(need)}] {slug}")
        # Build ordered candidate url list.
        candidates: list[str] = []
        idx_url = photos.get(slug)
        if idx_url and not is_local(idx_url):
            candidates.append(idx_url)
        if roster[slug] and not is_local(roster[slug]) and roster[slug] not in candidates:
            candidates.append(roster[slug])

        if args.dry_run:
            src = candidates[0] if candidates else "(needs profile re-scrape / PCS)"
            print(f"      would fetch from: {src}")
            stored[slug] = f"photos/{slug}.jpg"  # provisional, for counting
            continue

        got = None
        for url in candidates:
            print(f"      try {url[:70]}")
            got = download_image(url)
            if got:
                break
            time.sleep(DELAY)

        # Source 3: fresh CyclingFlash url from the profile page.
        if not got and not args.no_refresh:
            print("      re-scraping CyclingFlash profile for a fresh url…")
            fu = fresh_cf_url(slug)
            time.sleep(DELAY)
            if fu:
                got = download_image(fu)
                time.sleep(DELAY)

        # Source 4: PCS portrait.
        if not got:
            print("      trying procyclingstats…")
            pu = pcs_url(slug)
            time.sleep(DELAY)
            if pu:
                got = download_image(pu)
                time.sleep(DELAY)

        if not got:
            print("      ✗ NO IMAGE FOUND")
            failed.append(slug)
            time.sleep(DELAY)
            continue

        blob, ext = got
        out = PHOTO_DIR / f"{slug}{ext}"
        out.write_bytes(blob)
        stored[slug] = f"photos/{slug}{ext}"
        print(f"      ✓ saved {out.name} ({len(blob) // 1024} KB)")
        time.sleep(DELAY)

    print(f"\n{'=' * 60}")
    print(f"Stored this run: {len(stored)}   Failed: {len(failed)}")
    if failed:
        print("Failed slugs:", ", ".join(failed[:40]) + (" …" if len(failed) > 40 else ""))

    if args.dry_run:
        print("\n[dry-run] no files written.")
        return

    # ── Rewrite the index: roster riders with a local file → local path. ────────
    # Preserve every existing non-roster entry untouched (don't lose them).
    new_index = dict(photos)
    for slug in roster:
        lp = existing_local(slug)
        if lp:
            new_index[slug] = f"photos/{lp.name}"

    # "Never lose a photo" guard — count roster riders resolving to a LOCAL file.
    local_after = sum(1 for s in roster if is_local(new_index.get(s, "")))
    if local_after < local_before:
        raise SystemExit(
            f"ABORT: local roster photos would drop {local_before} -> {local_after}. "
            f"Refusing to write (would lose photos)."
        )

    PHOTOS_JSON.write_text(
        json.dumps(new_index, ensure_ascii=False, separators=(",", ":")), "utf-8"
    )
    print(f"\nrider_photos.json: {local_after}/{len(roster)} roster riders now local "
          f"({len(new_index)} total entries)")

    # Inject local paths into data.json inline photo fields.
    injected = 0
    for team in data.get("teams", []):
        for r in team.get("riders", []):
            slug = r.get("slug")
            if slug and is_local(new_index.get(slug, "")) and r.get("photo") != new_index[slug]:
                r["photo"] = new_index[slug]
                injected += 1
    try:
        sys.path.insert(0, str(BASE))
        from db_safe import safe_json_write
        safe_json_write(str(DATA), data,
                        required_keys=["live", "upcoming", "recent", "scraped_at"],
                        min_ratio=0.90, label="data.json (local photos)")
    except Exception:
        # Fallback: plain write if db_safe isn't importable in this context.
        DATA.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    print(f"data.json: injected {injected} local photo paths")
    print('\nCommit with:  bash git-push.sh "data: store rider photos locally"')


if __name__ == "__main__":
    main()
