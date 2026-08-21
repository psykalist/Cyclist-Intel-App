#!/usr/bin/env python3
"""
fetch_missing_photos.py — RETIRED (Aug 2026).

This script scraped CyclingFlash for rider photo *URLs* and stored those URLs in
rider_photos.json / data.json, so the app hotlinked them at render time. When
CyclingFlash's CDN stopped allowing hotlinks, every CF-hosted rider went blank.

Replacement:  fetch_rider_photos_local.py  — downloads the image BYTES once into
photos/<slug>.<ext> and points the app at the local path, so nothing external
can ever blank the roster again.

This file is intentionally inert. It exits without touching any data.
"""
import sys

print(__doc__)
print("fetch_missing_photos.py is retired — use fetch_rider_photos_local.py. No action taken.")
sys.exit(0)
