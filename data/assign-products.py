#!/usr/bin/env python3
"""
Product assignment pass for pipeline.json.
For each article, calls Claude to reason through which products to assign
based on keyword, type, angle, and available products in that cluster.

Outputs updated pipeline.json with products[] and assignment_notes filled.
Run with --dry-run to preview without writing. Use --id to run a single article.
"""

import json
import yaml
import anthropic
import argparse
import os
import time
from pathlib import Path

PIPELINE_PATH = Path(__file__).parent / "pipeline.json"
PRODUCTS_PATH = Path(__file__).parent.parent / "content/products/products.yaml"
OUT_PATH = PIPELINE_PATH  # overwrite in-place (we backup first)


def load_products() -> dict:
    with open(PRODUCTS_PATH) as f:
        raw = yaml.safe_load(f)
    # Convert to serializable dict
    products = {}
    for key, p in raw.items():
        products[key] = {
            "key": key,
            "name": p.get("name", ""),
            "brand": p.get("brand", ""),
            "cluster": p.get("category", ""),  # 'category' field holds the cluster slug
            "price_band": p.get("price_band", ""),
            "amazon_asin": p.get("amazon_asin", ""),
            "notes_for_writers": p.get("notes_for_writers", ""),
        }
    return products


def products_for_cluster(products: dict, cluster: str) -> list:
    return [p for p in products.values() if p["cluster"] == cluster]


SYSTEM = """You are a product assignment assistant for a gardening affiliate review site called The Four Season Gardener.
Your job is to assign the right products from a catalog to each article in the editorial pipeline.

Assignment rules by article type:
- Review: assign exactly 1 product — the primary subject of the review (match brand/model in keyword)
- Roundup (best-of list): assign 4–7 products with a spread across price bands (budget, mid, premium)
- Comparison: assign exactly 2 products being compared head-to-head
- Buyer Guide: assign 3–5 products as curated recommendations
- Informational (how-to/explainer): assign 0–2 products if contextually relevant; often 0

For each article, return a JSON object with:
{
  "products": ["product-key-1", "product-key-2"],
  "assignment_notes": "brief explanation of why these products were chosen"
}

Be specific in assignment_notes: explain why each product was chosen, what price spread or comparison logic applies, and flag anything uncertain.
Only use product keys from the catalog provided. Never invent product keys."""


def assign_products(article: dict, cluster_products: list, client: anthropic.Anthropic) -> dict:
    catalog_text = "\n".join(
        f"- {p['key']}: {p['name']} ({p['brand']}, {p['price_band']} price, ASIN {p['amazon_asin']}) — {p['notes_for_writers']}"
        for p in cluster_products
    )

    prompt = f"""Article to assign products for:
Keyword: {article['keyword']}
Type: {article['type']}
Cluster: {article['cluster']}
Angle: {article['angle']}
H2 structure: {article['h2_structure']}

Available products in this cluster ({article['cluster']}):
{catalog_text}

Assign the right products for this article. Return JSON only, no other text."""

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    # Strip markdown code fences if present
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break

    # Extract JSON object even if there's surrounding text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    result = json.loads(text)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print assignments without writing")
    parser.add_argument("--id", type=int, help="Assign only this article ID")
    parser.add_argument("--unassigned-only", action="store_true", default=True,
                        help="Only process articles with empty products list (default: True)")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # Try reading from credentials.env
        creds_path = Path(__file__).parent.parent / "config/credentials.env"
        if creds_path.exists():
            for line in creds_path.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"')
                    break
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found")

    client = anthropic.Anthropic(api_key=api_key)
    products = load_products()

    with open(PIPELINE_PATH) as f:
        pipeline = json.load(f)

    # Backup
    if not args.dry_run:
        backup = PIPELINE_PATH.with_suffix(".json.bak")
        with open(backup, "w") as f:
            json.dump(pipeline, f, indent=2)

    articles_to_process = pipeline
    if args.id:
        articles_to_process = [a for a in pipeline if a["id"] == args.id]
    elif args.unassigned_only:
        articles_to_process = [a for a in pipeline if not a.get("products")]

    print(f"Processing {len(articles_to_process)} articles...")

    for i, article in enumerate(articles_to_process):
        cluster = article["cluster"]
        cluster_prods = products_for_cluster(products, cluster)

        if not cluster_prods:
            print(f"  [{article['id']}] SKIP — no products for cluster '{cluster}'")
            article["assignment_notes"] = f"No products in catalog for cluster '{cluster}'"
            continue

        try:
            result = assign_products(article, cluster_prods, client)
            assigned = result.get("products", [])
            notes = result.get("assignment_notes", "")

            # Validate keys exist
            valid = [k for k in assigned if k in products]
            invalid = [k for k in assigned if k not in products]
            if invalid:
                notes += f" [INVALID KEYS REMOVED: {invalid}]"

            article["products"] = valid
            article["assignment_notes"] = notes

            print(f"  [{article['id']}] {article['type']:12} {article['keyword'][:50]}")
            print(f"    → {valid}")
            print(f"    {notes[:100]}")

        except Exception as e:
            print(f"  [{article['id']}] ERROR: {e}")
            article["assignment_notes"] = f"Assignment failed: {e}"

        # Small delay to avoid rate limits
        if i < len(articles_to_process) - 1:
            time.sleep(0.3)

    if not args.dry_run:
        with open(OUT_PATH, "w") as f:
            json.dump(pipeline, f, indent=2)
        print(f"\nWritten to {OUT_PATH}")
    else:
        print("\nDry run — no file written.")


if __name__ == "__main__":
    main()
