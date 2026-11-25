"""Download the openly licensed photos in data/damage/licensed/manifest.json and downsize them.

Run: uv run --all-packages python data/fetch_licensed_photos.py

Each photo's license, author and source are in the manifest; data/damage/README.md credits them.
Only public-domain and attribution-only licenses are accepted (see images.ALLOWED_LICENSES).
"""

from __future__ import annotations

import io
import time
import urllib.request
from pathlib import Path

from freight_agents.damage_assessor.images import load_manifest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
LICENSED = ROOT / "data" / "damage" / "licensed"
LONG_SIDE = 640
USER_AGENT = "dataset-fetch/0.1 (research script)"
WIKIMEDIA = ("https://upload.wikimedia.org/", "https://thumb.wikimedia.org/")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return bytes(response.read())


def downsize(raw: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(raw))
    if image.mode in ("RGBA", "LA", "P"):
        flat = Image.new("RGB", image.size, (255, 255, 255))
        flat.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
        image = flat
    image = image.convert("RGB")
    image.thumbnail((LONG_SIDE, LONG_SIDE))
    return image


if __name__ == "__main__":
    for photo in load_manifest(LICENSED / "manifest.json"):
        if not photo.download_url.startswith(WIKIMEDIA):
            raise SystemExit(f"{photo.id}: refusing to fetch from {photo.download_url}")
        downsize(fetch(photo.download_url)).save(LICENSED / photo.label.image, quality=85)
        print(f"{photo.id}: {photo.license}, {photo.author}")
        time.sleep(1)  # be polite to Wikimedia
