"""
Build JSON-LD schema blocks for FSG articles.
Generates Article, FAQPage, and BreadcrumbList schemas.
"""

import json
import re
import yaml
from pathlib import Path

ROOT = Path(__file__).parent.parent
SITE_URL = "https://fourseasongardener.com"


def _load_nav() -> dict:
    nav_path = ROOT / "config/navigation.yaml"
    return yaml.safe_load(nav_path.read_text())


def _hub_to_category(hub_slug: str):
    """Return {label, slug} for the category containing hub_slug."""
    nav = _load_nav()
    for cat in nav.get("categories", []):
        for hub in cat.get("hubs", []):
            if hub["slug"] == hub_slug:
                return {"label": cat["label"], "slug": cat["slug"],
                        "hub_label": hub["label"], "hub_slug": hub["slug"]}
    return None


def parse_faq(body: str) -> list:
    """Extract FAQ Q&A pairs from article body markdown."""
    faq_section = re.search(r'## Frequently Asked Questions\s*(.*?)(?=\n## |\Z)',
                            body, re.DOTALL)
    if not faq_section:
        return []

    faq_text = faq_section.group(1)
    pairs = []

    # Split on H3 headings
    chunks = re.split(r'\n### ', faq_text)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.splitlines()
        question = lines[0].strip().lstrip('#').strip()
        answer_lines = [l for l in lines[1:] if l.strip() and not l.startswith('!')]
        answer = ' '.join(answer_lines).strip()
        if question and answer:
            pairs.append({"q": question, "a": answer})

    return pairs[:5]


def build_schema(article_data: dict, body: str) -> str:
    """Build all three JSON-LD schema blocks and return as HTML string."""
    slug = article_data.get("slug", "")
    title = article_data.get("title", "")
    description = article_data.get("description", "")
    date = str(article_data.get("date", ""))[:10]
    hub_slug = article_data.get("hub", "")
    category_info = _hub_to_category(hub_slug)

    article_url = f"{SITE_URL}/{slug}/"

    # ── Article schema ────────────────────────────────────────────────────────
    article_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "datePublished": date,
        "dateModified": date,
        "mainEntityOfPage": {"@type": "WebPage", "@id": article_url},
        "author": {
            "@type": "Person",
            "name": "Wendy Hartley",
            "url": f"{SITE_URL}/about/"
        },
        "publisher": {
            "@type": "Organization",
            "name": "The Four Season Gardener",
            "url": SITE_URL
        }
    }

    # ── FAQ schema ────────────────────────────────────────────────────────────
    faq_pairs = parse_faq(body)
    faq_schema = None
    if faq_pairs:
        faq_schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": p["q"],
                    "acceptedAnswer": {"@type": "Answer", "text": p["a"]}
                }
                for p in faq_pairs
            ]
        }

    # ── Breadcrumb schema ─────────────────────────────────────────────────────
    breadcrumb_items = [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_URL}/"}
    ]
    if category_info:
        breadcrumb_items.append({
            "@type": "ListItem", "position": 2,
            "name": category_info["label"],
            "item": f"{SITE_URL}/{category_info['slug']}/"
        })
        breadcrumb_items.append({
            "@type": "ListItem", "position": 3,
            "name": category_info["hub_label"],
            "item": f"{SITE_URL}/{category_info['hub_slug']}/"
        })
    breadcrumb_items.append({
        "@type": "ListItem", "position": len(breadcrumb_items) + 1,
        "name": title,
        "item": article_url
    })

    breadcrumb_schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": breadcrumb_items
    }

    # ── Assemble HTML ─────────────────────────────────────────────────────────
    blocks = [article_schema, breadcrumb_schema]
    if faq_schema:
        blocks.append(faq_schema)

    html = "\n".join(
        f'<script type="application/ld+json">\n{json.dumps(s, indent=2)}\n</script>'
        for s in blocks
    )
    return f"\n\n{html}\n"
