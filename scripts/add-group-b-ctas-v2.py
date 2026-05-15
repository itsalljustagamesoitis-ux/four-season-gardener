#!/usr/bin/env python3
"""
Group B CTA Insertion - Round 2
Adds additional CTAs to still-underperforming review articles.
Handles more heading variants and adds Quick Verdict CTAs.
"""

import os
import re
import yaml

ARTICLES_DIR = "/Users/keithlacy/four-season-gardener/content/articles"
PRODUCTS_YAML = "/Users/keithlacy/four-season-gardener/content/products/products.yaml"

GROUP_A = {"garden-shed-with-loft", "birdies-metal-raised-garden-beds", "robot-lawn-mower-garage"}

# Articles that still need more CTAs (from audit: density < 1.8, word_count >= 2000)
TARGET_ARTICLES = {
    "aluminum-greenhouse-frame-kit",
    "tractor-leaf-blower",
    "solar-bird-bath-bubbler",
    "round-teak-outdoor-dining-set",
    "bird-feeder-ring",
    "rose-garden-gloves",
    "vego-elevated-garden-bed",
    "dewalt-cordless-lawn-mower",
    "teak-glider-bench",
    "orbit-smart-sprinkler-controller",
    "orbit-battery-operated-sprinkler-timer",
    "teak-porch-swing",
    "adirondack-sunbrella-chair-cushions",
    "ego-hedge-trimmer-with-battery-and-charger",
    "polywood-glider-bench",
    "stihl-battery-powered-chainsaws",
}


def load_products():
    with open(PRODUCTS_YAML) as f:
        return yaml.safe_load(f)


def get_primary_product_id(content):
    """Extract primary product ID from frontmatter."""
    m = re.search(r'products:\s*\n(?:\s*-[^\n]*\n)*\s*-\s*id:\s*["\']?([^"\'>\n]+)["\']?', content)
    if m:
        return m.group(1).strip()
    return None


def get_product_name(product_id, products_data):
    if product_id in products_data:
        return products_data[product_id].get("name", product_id)
    return product_id


def count_ctas(body):
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


def insert_cta_after_section(body, section_pattern, product_id, cta_text, stop_pattern=None):
    """Insert a CTA after the end of a section (before next ##-level heading)."""
    section_match = re.search(section_pattern, body, re.MULTILINE | re.IGNORECASE)
    if not section_match:
        return body, False

    search_start = section_match.start()
    # Find the next heading at same or higher level
    if stop_pattern:
        next_h = re.search(stop_pattern, body[search_start + 3:], re.MULTILINE | re.IGNORECASE)
    else:
        next_h = re.search(r'^##\s', body[search_start + 3:], re.MULTILINE)

    if not next_h:
        # Insert at end of content before FAQ or end
        faq_match = re.search(r'^##\s+Frequently', body[search_start:], re.MULTILINE | re.IGNORECASE)
        if faq_match:
            insert_pos = search_start + faq_match.start()
        else:
            insert_pos = len(body)
    else:
        insert_pos = search_start + 3 + next_h.start()

    before = body[:insert_pos].rstrip()
    after = body[insert_pos:]
    cta_block = f'\n\n{cta_text}\n\n'
    return before + cta_block + after, True


def add_ctas_to_article(filepath, products_data):
    """Add more CTAs to a specific article."""
    with open(filepath, encoding='utf-8') as f:
        content = f.read()

    slug = os.path.basename(filepath)[:-3]

    if not content.startswith("---"):
        return False, 0, "No frontmatter"

    end = content.find("\n---", 3)
    if end == -1:
        return False, 0, "Malformed frontmatter"

    header = content[:end + 4]
    body = content[end + 4:]

    product_id = get_primary_product_id(content)
    if not product_id:
        return False, 0, "No primary product ID"

    product_name = get_product_name(product_id, products_data)
    initial_ctas = count_ctas(body)
    placements = 0

    # Strategy: add CTAs in positions not already covered
    # 1. After Quick Verdict (if not already there)
    qv_match = re.search(r'^(##\s+Quick Verdict.*?)(?=^##)', body, re.MULTILINE | re.DOTALL)
    if qv_match:
        # Check if there's already a CTA immediately after Quick Verdict
        qv_end = qv_match.end()
        after_qv = body[qv_match.start():qv_end]
        if 'product:' not in after_qv or after_qv.count('product:') < 2:
            # Insert before the next heading after Quick Verdict
            next_h_pos = qv_match.start() + re.search(r'^##\s', body[qv_match.start() + 3:], re.MULTILINE).start() + 3
            before = body[:next_h_pos].rstrip()
            after = body[next_h_pos:]
            cta = f'\n\n[Check current price on Amazon](product:{product_id})\n\n'
            body = before + cta + after
            placements += 1

    # 2. After "## What We Tested" or "## Performance" (for articles without Key Specs)
    if placements == 0 or count_ctas(body) - initial_ctas < 2:
        # Try inserting after the first big performance/testing section
        for section_pat in [
            r'^##\s+(?:What We Tested|Performance and Testing|Performance|Testing)',
            r'^##\s+(?:Key Specs|Specs|Specifications)',
        ]:
            new_body, inserted = insert_cta_after_section(
                body, section_pat, product_id,
                f'[Check current price on Amazon](product:{product_id})'
            )
            if inserted:
                body = new_body
                placements += 1
                break

    # 3. After "## Who Should Buy This" or other "Who" variants
    who_patterns = [
        r'^##\s+Who Should Buy',
        r'^##\s+Who Is This For',
        r'^##\s+Who It\'s For',
        r'^##\s+Who This Is For',
    ]
    for pat in who_patterns:
        who_match = re.search(pat, body, re.MULTILINE | re.IGNORECASE)
        if who_match:
            # Check if already has CTA in this section
            after_who = body[who_match.start():]
            next_faq = re.search(r'^##\s+Frequently', after_who, re.MULTILINE | re.IGNORECASE)
            if next_faq:
                who_section = after_who[:next_faq.start()]
                if 'product:' not in who_section:
                    insert_pos = who_match.start() + next_faq.start()
                    before = body[:insert_pos].rstrip()
                    after = body[insert_pos:]
                    cta = f'\n\n[See {product_name} on Amazon →](product:{product_id})\n\n'
                    body = before + cta + after
                    placements += 1
            break

    final_ctas = count_ctas(body)
    actual_added = final_ctas - initial_ctas

    if actual_added > 0:
        new_content = header + body
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True, actual_added, f"Added {actual_added} CTAs (total now: {final_ctas})"
    return False, 0, "No new CTAs added"


def main():
    products_data = load_products()
    modified_count = 0

    for slug in sorted(TARGET_ARTICLES):
        filepath = os.path.join(ARTICLES_DIR, f"{slug}.md")
        if not os.path.exists(filepath):
            print(f"  NOT FOUND: {slug}")
            continue

        modified, added, reason = add_ctas_to_article(filepath, products_data)
        if modified:
            modified_count += 1
            print(f"  MODIFIED {slug}: {reason}")
        else:
            print(f"  NO CHANGE {slug}: {reason}")

    print(f"\nTotal articles modified in round 2: {modified_count}")


if __name__ == "__main__":
    main()
