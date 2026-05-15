#!/usr/bin/env python3
"""
Group B CTA Insertion Script for fourseasongardener.com
Adds Amazon CTAs to review articles with low CTA density.
"""

import os
import re
import yaml

ARTICLES_DIR = "/Users/keithlacy/four-season-gardener/content/articles"
PRODUCTS_YAML = "/Users/keithlacy/four-season-gardener/content/products/products.yaml"

GROUP_A = {"garden-shed-with-loft", "birdies-metal-raised-garden-beds", "robot-lawn-mower-garage"}

MIN_WORDS = 2000
MAX_CTAS_THRESHOLD = 5  # Only process if currently <= 5 CTAs


def load_products():
    with open(PRODUCTS_YAML) as f:
        return yaml.safe_load(f)


def parse_frontmatter(content):
    if not content.startswith("---"):
        return {}, content, ""
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content, ""
    fm_raw = content[3:end]
    body = content[end + 4:]

    fm = {}
    for line in fm_raw.split("\n"):
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, body, fm_raw


def get_primary_product_id(content):
    """Extract primary product ID from frontmatter."""
    fm_match = re.search(r'products:\s*\n(?:\s*-[^\n]*\n)*\s*-\s*id:\s*["\']?([^"\'>\n]+)["\']?', content)
    if fm_match:
        return fm_match.group(1).strip()
    return None


def get_product_name(product_id, products_data):
    """Get product name from products data."""
    if product_id in products_data:
        return products_data[product_id].get("name", product_id)
    return product_id


def count_ctas(body):
    """Count total CTAs (product: links + amazon URLs + btn--amazon)."""
    product_links = re.findall(r'\[(?:[^\]]+)\]\(product:[^)]+\)', body)
    amazon_urls = re.findall(r'https?://(?:www\.)?amazon\.com[^\s\)\"\']*|https?://amzn\.to[^\s\)\"\']*', body)
    btn_ctas = re.findall(r'btn--amazon', body)
    return len(product_links) + len(amazon_urls) + len(btn_ctas)


def count_words(body):
    text = re.sub(r'<[^>]+>', ' ', body)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`[^`]*`', ' ', text)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    return len(text.split())


def is_review(fm, body):
    article_type = fm.get("type", "")
    if article_type == "review":
        return True
    if re.search(r'^##\s+Quick Verdict', body, re.MULTILINE):
        return True
    return False


def is_roundup(fm):
    return fm.get("type", "") in ("roundup", "comparison", "buyer_guide")


def insert_after_key_specs(body, product_id, product_name):
    """Insert CTA after Key Specs section content."""
    # Find "## Key Specs" section
    specs_match = re.search(r'^(##\s+Key Specs.*?)(?=^##|\Z)', body, re.MULTILINE | re.DOTALL)
    if not specs_match:
        # Try variations
        specs_match = re.search(r'^(###\s+Key Specs.*?)(?=^##|^###|\Z)', body, re.MULTILINE | re.DOTALL)

    if specs_match:
        specs_section = specs_match.group(1)
        # Find end of specs section
        specs_end = specs_match.end()
        cta_line = f'\n[Check current price on Amazon](product:{product_id})\n'

        # Insert before the next heading
        next_heading = re.search(r'^##', body[specs_match.start():], re.MULTILINE)
        if next_heading:
            insert_pos = specs_match.start() + next_heading.start()
            body = body[:insert_pos] + cta_line + '\n' + body[insert_pos:]
            return body, True
    return body, False


def insert_after_pros_cons(body, product_id, product_name):
    """Insert CTA after Pros and Cons section."""
    # Find "## Pros and Cons" or similar
    pros_pattern = re.compile(
        r'^(##\s+(?:Pros and Cons|Pros & Cons|What Works|Pros/Cons).*?)(?=^##|\Z)',
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    pros_match = pros_pattern.search(body)

    if pros_match:
        next_heading = re.search(r'^##', body[pros_match.start() + 3:], re.MULTILINE)
        if next_heading:
            insert_pos = pros_match.start() + 3 + next_heading.start()
            # Find the line before this heading
            before = body[:insert_pos].rstrip()
            after = body[insert_pos:]
            cta_line = f'\n\n[See {product_name} on Amazon →](product:{product_id})\n\n'
            body = before + cta_line + after
            return body, True
    return body, False


def insert_in_who_its_for(body, product_id, product_name):
    """Insert CTA in or after Who It's For section."""
    who_pattern = re.compile(
        r'^(##\s+Who(?:\'s| It\'s| It Is) For.*?)(?=^##\s+Frequently|\Z)',
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )
    who_match = who_pattern.search(body)

    if who_match:
        who_section = who_match.group(1)
        who_end = who_match.end()

        # Find the last paragraph of Who It's For (before next heading)
        next_faq = re.search(r'^##\s+Frequently', body[who_match.start():], re.MULTILINE | re.IGNORECASE)
        if next_faq:
            insert_pos = who_match.start() + next_faq.start()
            before = body[:insert_pos].rstrip()
            after = body[insert_pos:]
            cta_line = f'\n\n[Check current price on Amazon](product:{product_id})\n\n'
            body = before + cta_line + after
            return body, True
    return body, False


def add_ctas_to_article(filepath, products_data, dry_run=False):
    """Add CTAs to a single article. Returns (modified, placements_added, reason_skipped)."""
    with open(filepath, encoding='utf-8') as f:
        content = f.read()

    slug = os.path.basename(filepath)[:-3]

    # Skip Group A
    if slug in GROUP_A:
        return False, 0, "Group A article (handled separately)"

    # Parse frontmatter
    if not content.startswith("---"):
        return False, 0, "No frontmatter"

    end = content.find("\n---", 3)
    if end == -1:
        return False, 0, "Malformed frontmatter"

    fm_block = content[3:end]
    body = content[end + 4:]
    header = content[:end + 4]

    fm = {}
    for line in fm_block.split("\n"):
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")

    # Check type
    if not is_review(fm, body):
        return False, 0, f"Not a review (type={fm.get('type', '?')})"

    if is_roundup(fm):
        return False, 0, "Roundup/comparison article"

    # Check word count
    wc = count_words(body)
    if wc < MIN_WORDS:
        return False, 0, f"Word count too low ({wc})"

    # Check existing CTA count
    existing_ctas = count_ctas(body)
    if existing_ctas > MAX_CTAS_THRESHOLD:
        return False, 0, f"Already has {existing_ctas} CTAs (> {MAX_CTAS_THRESHOLD})"

    # Get primary product ID
    product_id = get_primary_product_id(content)
    if not product_id:
        return False, 0, "No primary product ID in frontmatter"

    product_name = get_product_name(product_id, products_data)

    # Apply insertions
    placements = 0
    modified_body = body

    # 1. After Key Specs
    modified_body, inserted = insert_after_key_specs(modified_body, product_id, product_name)
    if inserted:
        placements += 1

    # 2. After Pros and Cons
    modified_body, inserted = insert_after_pros_cons(modified_body, product_id, product_name)
    if inserted:
        placements += 1

    # 3. In Who It's For
    modified_body, inserted = insert_in_who_its_for(modified_body, product_id, product_name)
    if inserted:
        placements += 1

    if placements == 0:
        return False, 0, "No suitable insertion points found"

    if not dry_run:
        new_content = header + modified_body
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

    return True, placements, f"Added {placements} CTAs for product:{product_id}"


def main():
    products_data = load_products()

    modified_count = 0
    skipped = []
    details = []

    for filename in sorted(os.listdir(ARTICLES_DIR)):
        if not filename.endswith(".md"):
            continue

        filepath = os.path.join(ARTICLES_DIR, filename)
        slug = filename[:-3]

        modified, placements, reason = add_ctas_to_article(filepath, products_data)

        if modified:
            modified_count += 1
            details.append(f"  MODIFIED {slug}: {reason}")
        else:
            skipped.append(f"  SKIPPED {slug}: {reason}")

    print(f"\n{'='*60}")
    print(f"GROUP B CTA INSERTION RESULTS")
    print(f"{'='*60}")
    print(f"Articles modified: {modified_count}")
    print(f"Articles skipped: {len(skipped)}")
    print(f"\nModified articles:")
    for d in details:
        print(d)
    print(f"\nSkipped articles (sample):")
    for s in skipped[:20]:
        print(s)
    if len(skipped) > 20:
        print(f"  ... and {len(skipped) - 20} more")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
