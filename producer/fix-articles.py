#!/usr/bin/env python3
"""
Retroactively fix all published articles:
- Inject schema (Article, FAQ, Breadcrumb) if not already present
- Re-generate articles that lack sibling links (articles generated in batch before fix)

Usage:
  python3 producer/fix-articles.py --schema-only      # just add schema, no regeneration
  python3 producer/fix-articles.py --regen-slugs      # list slugs that need regeneration
  python3 producer/fix-articles.py --regen            # regenerate articles missing sibling links
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "producer"))

from data_loader import load_pipeline, load_products, load_persona, load_eeat_vault, save_pipeline, get_eeat_for_cluster
from article_builder import generate_article, build_frontmatter
from publish import inject_body_images
from schema_builder import build_schema

ARTICLES_DIR = ROOT / "content/articles"


def has_schema(content: str) -> bool:
    return 'application/ld+json' in content


def has_sibling_links(content: str, pipeline: list, article: dict) -> bool:
    """Check if article links to any sibling articles."""
    siblings = [a for a in pipeline
                if a["cluster"] == article["cluster"]
                and a["status"] == "published"
                and a["slug"] != article["slug"]]
    if not siblings:
        return True  # no siblings to link to
    return any(f'/{s["slug"]}/' in content for s in siblings)


def inject_schema_only(path: Path, pipeline: list) -> bool:
    """Add schema to an existing article file. Returns True if changed."""
    content = path.read_text(encoding="utf-8")
    if has_schema(content):
        return False

    # Get article metadata from frontmatter
    slug = path.stem
    article = next((a for a in pipeline if a["slug"] == slug), None)
    if not article:
        return False

    # Extract title and description from frontmatter
    import re
    title = re.search(r'^title: "(.+)"', content, re.MULTILINE)
    desc = re.search(r'^description: "(.+)"', content, re.MULTILINE)
    hub = re.search(r'^hub: "(.+)"', content, re.MULTILINE)
    date = re.search(r'^date: (.+)', content, re.MULTILINE)

    article_data = {
        "slug": slug,
        "title": title.group(1) if title else slug,
        "description": desc.group(1) if desc else "",
        "hub": hub.group(1) if hub else article.get("hub_slug", ""),
        "date": date.group(1).strip() if date else "2026-05-01",
    }

    # Extract body (after frontmatter)
    body_match = re.search(r'^---\n.*?^---\n(.+)', content, re.DOTALL | re.MULTILINE)
    body = body_match.group(1) if body_match else content

    schema = build_schema(article_data, body)
    path.write_text(content.rstrip() + schema + "\n", encoding="utf-8")
    return True


def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    creds = ROOT / "config/credentials.env"
    if creds.exists():
        for line in creds.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    oi_creds = Path.home() / "ordinary-introvert/config/credentials.env"
    if oi_creds.exists():
        for line in oi_creds.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    raise ValueError("ANTHROPIC_API_KEY not found")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema-only", action="store_true", help="Only inject schema, no regeneration")
    parser.add_argument("--regen-slugs", action="store_true", help="List articles that need regeneration")
    parser.add_argument("--regen", action="store_true", help="Regenerate articles missing sibling links")
    args = parser.parse_args()

    pipeline = load_pipeline()
    published = [a for a in pipeline if a["status"] == "published"]

    # ── Schema injection pass ──────────────────────────────────────────────────
    print(f"Schema injection pass ({len(published)} published articles)...")
    schema_added = 0
    for article in published:
        path = ARTICLES_DIR / f"{article['slug']}.md"
        if not path.exists():
            continue
        if inject_schema_only(path, pipeline):
            schema_added += 1
            print(f"  + schema → {article['slug']}")
    print(f"Schema added to {schema_added} articles.\n")

    if args.schema_only:
        return

    # ── Find articles needing sibling links ────────────────────────────────────
    needs_regen = []
    for article in published:
        path = ARTICLES_DIR / f"{article['slug']}.md"
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if not has_sibling_links(content, pipeline, article):
            needs_regen.append(article)

    print(f"Articles missing sibling links: {len(needs_regen)}")
    for a in needs_regen:
        print(f"  - {a['slug']} (cluster: {a['cluster']})")

    if args.regen_slugs or not args.regen:
        return

    # ── Regenerate articles missing sibling links ──────────────────────────────
    print(f"\nRegenerating {len(needs_regen)} articles...\n")
    import anthropic
    client = anthropic.Anthropic(api_key=get_api_key())
    products = load_products()
    persona = load_persona()
    vault = load_eeat_vault()

    for i, article in enumerate(needs_regen):
        slug = article["slug"]
        print(f"[{i+1}/{len(needs_regen)}] {article['type']} — {article['keyword']}", end="", flush=True)

        # Attach siblings
        article["_siblings"] = [
            a for a in pipeline
            if a["cluster"] == article["cluster"]
            and a["status"] == "published"
            and a["slug"] != slug
        ]

        eeat = get_eeat_for_cluster(vault, article["cluster"])

        try:
            body, title, description = generate_article(article, products, eeat, persona, client)
            frontmatter = build_frontmatter(article, products, title, description)
            body_with_images = inject_body_images(body, article.get("body_images", []))
            schema = build_schema({"slug": slug, "title": title, "description": description,
                                   "date": "2026-05-01", "hub": article.get("hub_slug", "")}, body)
            md_content = frontmatter + body_with_images + schema + "\n"
            out_path = ARTICLES_DIR / f"{slug}.md"
            out_path.write_text(md_content, encoding="utf-8")
            print(f" done. {len(body.split())} words")
        except Exception as e:
            print(f" ERROR: {e}")
            continue

        if i < len(needs_regen) - 1:
            time.sleep(1)

    # Strip temporary _siblings key before saving
    for a in pipeline:
        a.pop("_siblings", None)
    save_pipeline(pipeline)
    print(f"\nDone. {len(needs_regen)} articles regenerated.")


if __name__ == "__main__":
    main()
