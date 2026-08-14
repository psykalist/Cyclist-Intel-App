#!/usr/bin/env python3
"""
build_rider_photos.py — Build a slim slug→photo_url index from rider_profiles.json.

Output: rider_photos.json  (~50KB vs 24MB for the full profiles file)

Run after any scrape_rider_profiles.py run:
  python build_rider_photos.py
  git add rider_photos.json && git commit -m "data: rebuild rider photos index" && git push
"""
import json, subprocess
from pathlib import Path

BASE = Path(__file__).parent
PROFILES = BASE / 'rider_profiles.json'
OUT = BASE / 'rider_photos.json'

def _renders(url):
    """Only keep photo URLs that actually load on our site. ProCyclingStats
    image URLs don't render when hotlinked from GitHub Pages, so exclude them —
    CyclingFlash CDN photos (added by fetch_missing_photos.py) are the good source."""
    return bool(url) and 'procyclingstats.com' not in url

riders = json.loads(PROFILES.read_text('utf-8')).get('riders', {})
profile_photos = {slug: r['photo'] for slug, r in riders.items()
                  if _renders(r.get('photo'))}

# MERGE into the existing index rather than overwriting it: fetch_missing_photos.py
# and scrape_teams.py write CyclingFlash CDN URLs straight into rider_photos.json,
# and those must not be clobbered by a profiles-only rebuild. Also strip any
# previously-stored PCS URLs so broken photos get cleaned out over time.
photos = {}
if OUT.exists():
    photos = {s: u for s, u in json.loads(OUT.read_text('utf-8')).items() if _renders(u)}
photos.update(profile_photos)
print(f'Riders with photos: {len(photos)} (merged; PCS URLs stripped)')

OUT.write_text(json.dumps(photos, ensure_ascii=False, separators=(',', ':')), 'utf-8')
size = OUT.stat().st_size // 1024
print(f'Written rider_photos.json ({size} KB)')

subprocess.run(['git', 'add', 'rider_photos.json'], cwd=BASE)
result = subprocess.run(['git', 'diff', '--staged', '--quiet'], cwd=BASE)
if result.returncode != 0:
    subprocess.run(['git', 'commit', '-m', f'data: rider photos index ({len(photos)} photos)'], cwd=BASE)
    subprocess.run(['git', 'push'], cwd=BASE)
    print('Committed and pushed.')
else:
    print('No changes.')
