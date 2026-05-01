#!/usr/bin/env python3
"""
Fetch Amazon product image URLs by ASIN and write them back to products.yaml.
Uses Amazon's product page (allowed under Associates ToS for affiliates).
"""

import re
import time
import sys
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).parent.parent
PRODUCTS_PATH = ROOT / "content/products/products.yaml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Patterns to extract the main product image from Amazon HTML
IMAGE_PATTERNS = [
    r'"hiRes"\s*:\s*"(https://m\.media-amazon\.com/images/I/[^"]+\.jpg)"',
    r'"large"\s*:\s*"(https://m\.media-amazon\.com/images/I/[^"]+\.jpg)"',
    r'data-old-hires="(https://m\.media-amazon\.com/images/I/[^"]+\.jpg)"',
    r'id="landingImage"[^>]+src="(https://m\.media-amazon\.com/images/I/[^"]+)"',
]


def fetch_image_url(asin: str):
    url = f"https://www.amazon.com/dp/{asin}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        for pattern in IMAGE_PATTERNS:
            m = re.search(pattern, r.text)
            if m:
                img = m.group(1)
                # Normalize to _SL500_ size
                img = re.sub(r'\._[A-Z0-9_,]+_\.', '._SL500_.', img)
                return img
    except Exception as e:
        print(f"  ERROR fetching {asin}: {e}")
    return None


def main():
    raw = PRODUCTS_PATH.read_text()
    products = yaml.safe_load(raw)

    updated = 0
    skipped = 0
    failed = []

    for pid, p in products.items():
        asin = p.get("amazon_asin")
        if not asin:
            skipped += 1
            continue

        current = p.get("default_image", "")
        if current.startswith("http"):
            skipped += 1
            continue

        print(f"  {pid} ({asin})...", end="", flush=True)
        img_url = fetch_image_url(asin)

        if img_url:
            p["default_image"] = img_url
            updated += 1
            print(f" ✓")
        else:
            failed.append(pid)
            print(f" ✗ not found")

        time.sleep(1.5)

    # Write back
    PRODUCTS_PATH.write_text(yaml.dump(products, allow_unicode=True, sort_keys=False, default_flow_style=False))
    print(f"\nDone. Updated: {updated}, Skipped: {skipped}, Failed: {len(failed)}")
    if failed:
        print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
