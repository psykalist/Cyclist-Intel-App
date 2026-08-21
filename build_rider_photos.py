#!/usr/bin/env python3
"""
build_rider_photos.py — RETIRED (Aug 2026).

This script built a slug→remote-URL index and MERGED remote CyclingFlash CDN
URLs into rider_photos.json. That is now actively harmful: rider photos are
stored as LOCAL files (photos/<slug>.<ext>) and rider_photos.json holds local
paths. Running the old merge would overwrite those local paths with remote URLs
and reintroduce the hotlink dependency that broke every CyclingFlash-hosted
rider.

Replacement:  fetch_rider_photos_local.py  (downloads + stores photos locally,
never overwrites an existing local file, never hotlinks).

This file is intentionally inert. It exits without touching any data.
"""
import sys

print(__doc__)
print("build_rider_photos.py is retired — use fetch_rider_photos_local.py. No action taken.")
sys.exit(0)
