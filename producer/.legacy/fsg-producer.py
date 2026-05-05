#!/usr/bin/env python3
"""
FSG Article Producer
Reads pipeline.json, generates articles via Claude, writes .md files to staging/.
Human review → move to src/content/articles/ to publish.

Usage:
  python3 producer/fsg-producer.py --id 3
  python3 producer/fsg-producer.py --count 10
  python3 producer/fsg-producer.py --count 5 --type Roundup
  python3 producer/fsg-producer.py --slug polywood-adirondack-chair-review
  python3 producer/fsg-producer.py --dry-run --count 5
"""

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "producer"))

import anthropic
from data_loader import (
    load_pipeline, load_products, load_persona, load_eeat_vault,
    get_pending_articles, get_article_by_id, get_article_by_slug,
    get_eeat_for_cluster, save_pipeline,
)
from article_builder import generate_article, build_frontmatter
from docx_writer import build_docx
from publish import inject_body_images
from schema_builder import build_schema

STAGING_DIR = ROOT / "staging"
ARTICLES_DIR = ROOT / "content/articles"
STAGING_DIR.mkdir(exist_ok=True)
(STAGING_DIR / "approved").mkdir(exist_ok=True)
ARTICLES_DIR.mkdir(parents=True, exist_ok=True)


def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    creds = ROOT / "config/credentials.env"
    if creds.exists():
        for line in creds.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    # Fall back to OI credentials
    oi_creds = Path.home() / "ordinary-introvert/config/credentials.env"
    if oi_creds.exists():
        for line in oi_creds.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    raise ValueError("ANTHROPIC_API_KEY not found. Set env var or add to config/credentials.env")


def select_articles(pipeline: list, args) -> list:
    if args.id:
        a = get_article_by_id(pipeline, args.id)
        return [a] if a else []
    if args.slug:
        a = get_article_by_slug(pipeline, args.slug)
        return [a] if a else []

    pending = get_pending_articles(pipeline)

    if args.type:
        pending = [a for a in pending if a["type"].lower() == args.type.lower()]

    if args.cluster:
        pending = [a for a in pending if a["cluster"] == args.cluster]

    # Sort: lower KD first (easier wins), then higher volume
    pending.sort(key=lambda a: (a.get("kd", 99), -a.get("volume", 0)))

    count = args.count or 1
    return pending[:count]


def already_staged(slug: str) -> bool:
    return (STAGING_DIR / f"{slug}.docx").exists() or (ARTICLES_DIR / f"{slug}.md").exists()


def mark_produced(pipeline: list, article_id: int) -> None:
    for a in pipeline:
        if a["id"] == article_id:
            a["status"] = "staged"
            break


def run(args):
    pipeline = load_pipeline()
    products = load_products()
    persona = load_persona()
    vault = load_eeat_vault()

    articles = select_articles(pipeline, args)

    if not articles:
        print("No matching pending articles found.")
        return

    print(f"Producing {len(articles)} article(s)...\n")

    client = anthropic.Anthropic(api_key=get_api_key()) if not args.dry_run else None

    for i, article in enumerate(articles):
        slug = article["slug"]
        print(f"[{i+1}/{len(articles)}] {article['type']} — {article['keyword']} (id: {article['id']})")

        if already_staged(slug) and not args.force:
            print(f"  SKIP — {slug}.md already in staging/. Use --force to regenerate.\n")
            continue

        if args.dry_run:
            print(f"  DRY RUN — would generate {slug}.md")
            print(f"  Products: {article.get('products', [])}")
            print(f"  Hub: {article.get('hub_label')} ({article.get('hub_url')})\n")
            continue

        eeat = get_eeat_for_cluster(vault, article["cluster"])

        # Attach published siblings in same cluster for internal linking
        article["_siblings"] = [
            a for a in pipeline
            if a["cluster"] == article["cluster"]
            and a["status"] == "published"
            and a["slug"] != article["slug"]
        ]

        try:
            print("  Generating...", end="", flush=True)
            body, title, description = generate_article(article, products, eeat, persona, client)
            word_count = len(body.split())

            if args.publish:
                # Write directly to content/articles/ — no human review step
                frontmatter = build_frontmatter(article, products, title, description)
                body_with_images = inject_body_images(body, article.get("body_images", []))
                schema = build_schema({"slug": slug, "title": title, "description": description,
                                       "date": str(__import__('datetime').date.today()),
                                       "hub": article.get("hub_slug", "")}, body)
                md_content = frontmatter + body_with_images + schema + "\n"
                out_path = ARTICLES_DIR / f"{slug}.md"
                out_path.write_text(md_content, encoding="utf-8")
                article["status"] = "published"
                print(f" done. {word_count} words → content/articles/{slug}.md")
            else:
                doc = build_docx(article, body, title, description)
                out_path = STAGING_DIR / f"{slug}.docx"
                doc.save(out_path)
                article["status"] = "staged"
                print(f" done. {word_count} words → staging/{slug}.docx")

            article.pop("_siblings", None)
            save_pipeline(pipeline)

        except Exception as e:
            print(f" ERROR: {e}")
            continue

        if i < len(articles) - 1:
            time.sleep(1)

    if args.publish:
        print(f"\nDone. {len(articles)} article(s) written to content/articles/")
    else:
        print(f"\nDone. Review files in {STAGING_DIR}/")
        print("Edit in Word or Pages, move to staging/approved/, then: python3 producer/publish.py --all")


def main():
    parser = argparse.ArgumentParser(description="FSG Article Producer")
    parser.add_argument("--id", type=int, help="Produce single article by pipeline ID")
    parser.add_argument("--slug", help="Produce single article by slug")
    parser.add_argument("--count", type=int, help="Number of articles to produce")
    parser.add_argument("--type", help="Filter by type: Roundup, Review, Comparison, Informational, Buyer Guide")
    parser.add_argument("--cluster", help="Filter by cluster slug")
    parser.add_argument("--dry-run", action="store_true", help="Plan without generating")
    parser.add_argument("--force", action="store_true", help="Regenerate even if already staged")
    parser.add_argument("--publish", action="store_true", help="Write directly to content/articles/ without staging")
    args = parser.parse_args()

    run(args)


if __name__ == "__main__":
    main()
