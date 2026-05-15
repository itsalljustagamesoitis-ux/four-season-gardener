#!/usr/bin/env python3
"""
CTA Audit Script for fourseasongardener.com
Audits Amazon CTA density in article markdown files.
"""

import os
import re
import csv
import sys

ARTICLES_DIR = "/Users/keithlacy/four-season-gardener/content/articles"
OUTPUT_CSV = "/Users/keithlacy/four-season-gardener/scripts/cta-audit.csv"
AMAZON_TAG = "fourseasong-20"
MIN_DENSITY = 1.8
MIN_WORDS = 2000

GROUP_A = {"garden-shed-with-loft", "birdies-metal-raised-garden-beds", "robot-lawn-mower-garage"}


def parse_frontmatter(content):
    """Extract frontmatter as a dict of key: raw-value strings."""
    fm = {}
    if not content.startswith("---"):
        return fm, content
    end = content.find("\n---", 3)
    if end == -1:
        return fm, content
    fm_block = content[3:end].strip()
    body = content[end + 4:].strip()

    for line in fm_block.split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm, body


def count_ctas(body):
    """Count Amazon CTAs and button CTAs in body text.

    CTAs are counted as:
    - Any [text](product:id) markdown link in the body (these resolve to Amazon affiliate links)
    - Any raw amazon.com or amzn.to URLs
    - Any btn--amazon HTML button CTAs
    """
    # Count product: links in the body (these are affiliate links to Amazon)
    product_links = re.findall(r'\[(?:[^\]]+)\]\(product:[^)]+\)', body, re.IGNORECASE)
    total_ctas = len(product_links)

    # Count raw amazon.com or amzn.to URLs (not inside product: links)
    amazon_url_matches = re.findall(r'https?://(?:www\.)?amazon\.com[^\s\)\"\']*|https?://amzn\.to[^\s\)\"\']*', body, re.IGNORECASE)
    total_ctas += len(amazon_url_matches)

    # Count btn--amazon HTML buttons
    btn_ctas = len(re.findall(r'btn--amazon', body, re.IGNORECASE))
    total_ctas += btn_ctas  # These may overlap with amazon.com URLs but count separately

    # Dedicated button-style CTAs (on their own line, for "button_ctas" column)
    # These are product: links that look like standalone CTAs
    button_ctas = len(re.findall(
        r'^\s*\[(?:Check[^\]]*|See[^\]]*Amazon|View[^\]]*Amazon|Buy[^\]]*Amazon|Shop[^\]]*Amazon|[^\]]*on Amazon[^\]]*)\]\(product:[^)]+\)\s*$',
        body, re.MULTILINE | re.IGNORECASE
    )) + btn_ctas

    return total_ctas, button_ctas


def count_words(body):
    """Count approximate words in body text (excluding images, code blocks, HTML)."""
    # Remove HTML blocks
    text = re.sub(r'<[^>]+>', ' ', body)
    # Remove markdown images
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    # Remove markdown links but keep text
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`[^`]*`', ' ', text)
    # Remove heading markers
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    words = text.split()
    return len(words)


def is_review(fm, body):
    """Determine if article is a review."""
    article_type = fm.get("type", "").strip('"').strip("'")
    if article_type == "review":
        return True
    # Check for Quick Verdict section
    if re.search(r'^##\s+Quick Verdict', body, re.MULTILINE):
        return True
    return False


def is_roundup_comparison(fm, body):
    """Detect roundup/comparison articles."""
    article_type = fm.get("type", "").strip('"').strip("'")
    return article_type in ("roundup", "comparison", "buyer_guide")


def audit_articles():
    results = []

    for filename in sorted(os.listdir(ARTICLES_DIR)):
        if not filename.endswith(".md"):
            continue

        slug = filename[:-3]
        filepath = os.path.join(ARTICLES_DIR, filename)

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        fm, body = parse_frontmatter(content)

        article_type = fm.get("type", "unknown").strip('"').strip("'")
        review = is_review(fm, body)
        roundup = is_roundup_comparison(fm, body)

        total_ctas, btn_ctas = count_ctas(body)
        word_count = count_words(body)

        density = (total_ctas / word_count * 1000) if word_count > 0 else 0.0

        flagged = (
            density < MIN_DENSITY
            and review
            and word_count >= MIN_WORDS
            and not roundup
        )

        results.append({
            "article_slug": slug,
            "type": article_type,
            "is_review": review,
            "total_ctas": total_ctas,
            "button_ctas": btn_ctas,
            "word_count": word_count,
            "density": round(density, 2),
            "flagged": flagged,
        })

    return results


def write_csv(results):
    fieldnames = ["article_slug", "type", "total_ctas", "button_ctas", "word_count", "density", "flagged"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in fieldnames})


def print_summary(results):
    total = len(results)
    reviews = [r for r in results if r["is_review"]]
    flagged = [r for r in results if r["flagged"]]
    roundups = [r for r in results if r["type"] in ("roundup", "comparison", "buyer_guide")]

    print(f"\n{'='*60}")
    print(f"CTA AUDIT SUMMARY")
    print(f"{'='*60}")
    print(f"Total articles: {total}")
    print(f"Review articles: {len(reviews)}")
    print(f"Roundup/comparison articles: {roundups and len(roundups)}")
    print(f"Flagged (low CTA density, review, >=2000 words): {len(flagged)}")

    if reviews:
        avg_density = sum(r["density"] for r in reviews) / len(reviews)
        print(f"\nReview articles avg CTA density: {avg_density:.2f} per 1000 words")

    print(f"\nFlagged articles (density < {MIN_DENSITY}/1000w, review, >={MIN_WORDS}w):")
    for r in sorted(flagged, key=lambda x: x["density"]):
        print(f"  {r['article_slug']}: {r['total_ctas']} CTAs, {r['word_count']} words, density={r['density']}")

    print(f"\nGroup A articles:")
    for r in results:
        if r["article_slug"] in GROUP_A:
            print(f"  {r['article_slug']}: type={r['type']}, {r['total_ctas']} CTAs, {r['word_count']} words, density={r['density']}, flagged={r['flagged']}")

    print(f"\nDensity distribution (review articles):")
    bands = {"0": 0, "0-0.5": 0, "0.5-1.0": 0, "1.0-1.5": 0, "1.5-2.0": 0, "2.0-3.0": 0, "3.0+": 0}
    for r in reviews:
        d = r["density"]
        if d == 0:
            bands["0"] += 1
        elif d < 0.5:
            bands["0-0.5"] += 1
        elif d < 1.0:
            bands["0.5-1.0"] += 1
        elif d < 1.5:
            bands["1.0-1.5"] += 1
        elif d < 2.0:
            bands["1.5-2.0"] += 1
        elif d < 3.0:
            bands["2.0-3.0"] += 1
        else:
            bands["3.0+"] += 1
    for band, count in bands.items():
        print(f"  density {band}: {count} articles")

    print(f"\nCSV written to: {OUTPUT_CSV}")
    print(f"{'='*60}\n")

    return {"avg_density_reviews": avg_density if reviews else 0, "flagged": flagged, "reviews": reviews}


if __name__ == "__main__":
    print("Running CTA audit...")
    results = audit_articles()
    write_csv(results)
    summary = print_summary(results)
