#!/usr/bin/env python3
"""
Publish a reviewed article from staging/ to src/content/articles/.

Reads staging/<slug>.txt (which you've edited),
extracts TITLE and DESC from the header,
wraps it in correct frontmatter,
writes src/content/articles/<slug>.md.

Usage:
  python3 producer/publish.py --slug 40v-cordless-leaf-blower
  python3 producer/publish.py --all   # publish everything in staging/approved/
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "producer"))

from data_loader import load_pipeline, load_products, get_article_by_slug, save_pipeline
from article_builder import build_frontmatter
from docx_writer import read_docx

STAGING_DIR = ROOT / "staging"
ARTICLES_DIR = ROOT / "content/articles"
ARTICLES_DIR.mkdir(parents=True, exist_ok=True)


def parse_txt(path: Path) -> tuple:
    """Extract title, description, and body from a review .txt file."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title = ""
    description = ""
    body_start = 0

    for i, line in enumerate(lines):
        if line.startswith("TITLE:"):
            title = line[6:].strip()
        elif line.startswith("DESC:"):
            description = line[5:].strip()
        elif line.strip().startswith("---") and i > 2:
            # Second divider — body starts after the info block
            body_start = i + 1
            break

    # Skip blank lines after the divider
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1

    body = "\n".join(lines[body_start:]).strip()
    return title, description, body


def inject_body_images(body: str, images: list) -> str:
    """Insert images evenly across H2 sections in the article body."""
    if not images:
        return body
    lines = body.splitlines()
    h2_indices = [i for i, l in enumerate(lines) if l.startswith("## ")]
    if not h2_indices:
        return body
    # Pick evenly-spaced H2 positions (skip the first H2 — too close to top)
    positions = h2_indices[1:] if len(h2_indices) > 1 else h2_indices
    step = max(1, len(positions) // len(images))
    insert_at = [positions[i * step] for i in range(min(len(images), len(positions)))]
    # Insert in reverse order so indices stay valid
    for pos, img in zip(reversed(insert_at), reversed(images[:len(insert_at)])):
        tag = f'\n![{img["alt"]}](/images/{img["path"]})\n'
        lines.insert(pos, tag)
    return "\n".join(lines)


def publish_one(slug: str, pipeline: list, products: dict, dry_run: bool = False) -> bool:
    docx_path = STAGING_DIR / f"{slug}.docx"
    if not docx_path.exists():
        docx_path = STAGING_DIR / "approved" / f"{slug}.docx"
        if not docx_path.exists():
            print(f"  ERROR: no staging file found for '{slug}'")
            return False

    article = get_article_by_slug(pipeline, slug)
    if not article:
        print(f"  ERROR: '{slug}' not found in pipeline.json")
        return False

    title, description, body = read_docx(docx_path)

    if not title:
        print(f"  WARNING: no TITLE line found in {txt_path.name} — using keyword as fallback")
        title = article["keyword"].title()
    if not description:
        print(f"  WARNING: no DESC line found in {txt_path.name} — leaving blank")

    frontmatter = build_frontmatter(article, products, title, description)
    body = inject_body_images(body, article.get("body_images", []))
    md_content = frontmatter + body + "\n"

    out_path = ARTICLES_DIR / f"{slug}.md"

    if dry_run:
        print(f"  DRY RUN → would write {out_path.relative_to(ROOT)}")
        print(f"  Title: {title}")
        print(f"  Desc ({len(description)} chars): {description}")
        print(f"  Body: {len(body.split())} words")
        return True

    out_path.write_text(md_content, encoding="utf-8")

    # Mark as published in pipeline
    for a in pipeline:
        if a["slug"] == slug:
            a["status"] = "published"
            break

    print(f"  Published → {out_path.relative_to(ROOT)}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Publish reviewed articles")
    parser.add_argument("--slug", help="Publish a single article by slug")
    parser.add_argument("--all", action="store_true", help="Publish all .txt files in staging/approved/")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pipeline = load_pipeline()
    products = load_products()

    if args.slug:
        slugs = [args.slug]
    elif args.all:
        approved_dir = STAGING_DIR / "approved"
        slugs = [f.stem for f in sorted(approved_dir.glob("*.docx"))]
        if not slugs:
            print("No .txt files found in staging/approved/")
            return
    else:
        parser.print_help()
        return

    print(f"Publishing {len(slugs)} article(s)...\n")
    ok = 0
    for slug in slugs:
        print(f"[{slug}]")
        if publish_one(slug, pipeline, products, dry_run=args.dry_run):
            ok += 1

    if not args.dry_run:
        save_pipeline(pipeline)

    print(f"\nDone. {ok}/{len(slugs)} published.")
    if ok:
        print("Run `npm run build` or check the dev server to verify.")


if __name__ == "__main__":
    main()
