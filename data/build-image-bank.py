#!/usr/bin/env python3
"""
Build a Pexels image bank for FSG articles.

For each cluster, searches Pexels with a curated search term,
downloads 8 images to public/images/articles/,
then assigns one hero image per article in pipeline.json (round-robin within cluster).

Usage:
  python3 data/build-image-bank.py           # download + assign all clusters
  python3 data/build-image-bank.py --assign-only  # skip download, just assign from existing bank
  python3 data/build-image-bank.py --cluster outdoor-furniture
"""

import argparse
import json
import os
import time
from pathlib import Path
import requests

ROOT = Path(__file__).parent.parent
IMAGES_DIR = ROOT / "public/images/articles"
PIPELINE_PATH = ROOT / "data/pipeline.json"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Curated Pexels search terms per cluster
CLUSTER_SEARCHES = {
    "outdoor-furniture":  "outdoor patio furniture garden",
    "fire-and-heat":      "fire pit outdoor patio evening",
    "lighting":           "garden lights outdoor lighting night",
    "structures":         "garden shed greenhouse pergola",
    "battery-equipment":  "lawn mower garden tools cordless",
    "lawn-care":          "lawn garden maintenance tools",
    "hand-tools":         "garden hand tools gloves",
    "raised-beds":        "raised garden bed vegetables",
    "composting":         "compost garden soil organic",
    "irrigation":         "garden watering irrigation hose",
    "birds-wildlife":     "bird feeder garden wildlife birds",
}

IMAGES_PER_CLUSTER = 8
IMAGE_WIDTH = 900
IMAGE_HEIGHT = 500


def get_api_key() -> str:
    creds = ROOT / "config/credentials.env"
    if creds.exists():
        for line in creds.read_text().splitlines():
            if line.startswith("PEXELS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        raise ValueError("PEXELS_API_KEY not found in config/credentials.env")
    return key


def search_pexels(query: str, api_key: str, per_page: int = 8) -> list:
    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": api_key},
        params={"query": query, "per_page": per_page, "orientation": "landscape"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("photos", [])


def download_image(url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"    download failed: {e}")
        return False


def build_bank(cluster: str, api_key: str) -> list:
    """Download images for a cluster, return list of saved filenames."""
    query = CLUSTER_SEARCHES.get(cluster, cluster.replace("-", " "))
    print(f"  Searching Pexels: '{query}'")

    photos = search_pexels(query, api_key, per_page=IMAGES_PER_CLUSTER)
    if not photos:
        print(f"  WARNING: no results for '{query}'")
        return []

    saved = []
    for i, photo in enumerate(photos, 1):
        # Use medium src — good quality, not enormous
        img_url = photo["src"].get("large", photo["src"].get("medium", ""))
        if not img_url:
            continue

        filename = f"{cluster}-{i}.jpg"
        dest = IMAGES_DIR / filename

        print(f"    [{i}/{len(photos)}] {filename} — {photo.get('photographer','')}", end="")
        if download_image(img_url, dest):
            print(" ✓")
            saved.append({
                "filename": filename,
                "path": f"articles/{filename}",
                "photographer": photo.get("photographer", ""),
                "photographer_url": photo.get("photographer_url", ""),
                "pexels_url": photo.get("url", ""),
                "pexels_id": photo.get("id"),
            })
        else:
            print(" ✗")

        time.sleep(0.2)

    return saved


BODY_IMAGE_COUNT = 5


def assign_images(pipeline: list, bank: dict) -> int:
    """Assign hero + body images round-robin within each cluster. Returns count updated."""
    cluster_counters = {}
    updated = 0

    for article in pipeline:
        cluster = article.get("cluster", "")
        images = bank.get(cluster, [])
        if not images:
            continue

        # Always reassign (re-run rebuilds cleanly)
        idx = cluster_counters.get(cluster, 0) % len(images)
        cluster_counters[cluster] = idx + 1

        article["hero_image"] = images[idx]["path"]
        article["hero_image_alt"] = article.get('keyword', '').title()

        # Assign body images: next N images after hero (wrap around pool)
        n = min(BODY_IMAGE_COUNT, len(images) - 1) if len(images) > 1 else 0
        body = []
        for offset in range(1, n + 1):
            img = images[(idx + offset) % len(images)]
            body.append({
                "path": img["path"],
                "alt": article.get('keyword', '').title(),
            })
        article["body_images"] = body
        updated += 1

    return updated


def save_pipeline(pipeline: list):
    tmp = PIPELINE_PATH.with_suffix(".json.tmp")
    bak = PIPELINE_PATH.with_suffix(".json.bak")
    with open(tmp, "w") as f:
        json.dump(pipeline, f, indent=2)
    import shutil
    shutil.copy2(PIPELINE_PATH, bak)
    os.replace(tmp, PIPELINE_PATH)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assign-only", action="store_true", help="Skip download, assign from existing bank")
    parser.add_argument("--cluster", help="Process a single cluster only")
    args = parser.parse_args()

    api_key = get_api_key()

    with open(PIPELINE_PATH) as f:
        pipeline = json.load(f)

    clusters = [args.cluster] if args.cluster else list(CLUSTER_SEARCHES.keys())

    # Build or load bank
    bank = {}  # cluster → list of image dicts

    if not args.assign_only:
        print(f"Downloading images for {len(clusters)} cluster(s)...\n")
        for cluster in clusters:
            print(f"[{cluster}]")
            saved = build_bank(cluster, api_key)
            bank[cluster] = saved
            print(f"  {len(saved)} images saved\n")
            time.sleep(0.5)
    else:
        # Reconstruct bank from existing files
        print("Scanning existing image bank...")
        for cluster in clusters:
            existing = sorted(IMAGES_DIR.glob(f"{cluster}-*.jpg"))
            bank[cluster] = [{"filename": f.name, "path": f"articles/{f.name}",
                               "photographer": "", "photographer_url": "", "pexels_url": "", "pexels_id": None}
                             for f in existing]
            print(f"  {cluster}: {len(bank[cluster])} images")

    # Assign to pipeline
    print("\nAssigning hero images to pipeline...")
    updated = assign_images(pipeline, bank)
    save_pipeline(pipeline)

    # Save attribution data for photo credits page
    attr_path = ROOT / "data/image-attribution.json"
    all_images = [img for imgs in bank.values() for img in imgs]
    with open(attr_path, "w") as f:
        json.dump(all_images, f, indent=2)

    total_images = sum(len(v) for v in bank.values())
    print(f"\nDone.")
    print(f"  Images downloaded: {total_images}")
    print(f"  Pipeline articles updated: {updated}")
    print(f"  Attribution data: data/image-attribution.json")
    print(f"\nAdd photo credits to your site using data/image-attribution.json")
    print(f"Pexels requires: photographer name + link to their Pexels profile.")


if __name__ == "__main__":
    main()
