#!/usr/bin/env python3
"""
Strip Article and BreadcrumbList JSON-LD blocks from article markdown.
Keeps FAQPage schema (useful, not duplicated by SchemaMarkup component).
"""
import re
import glob
import os

ARTICLES_DIR = "content/articles"

def strip_schema_blocks(content: str) -> tuple[str, int]:
    """Remove Article and BreadcrumbList JSON-LD script blocks. Return (new_content, count_removed)."""
    pattern = re.compile(
        r'<script type="application/ld\+json">\s*\{[^<]*?"@type"\s*:\s*"(Article|Review|BreadcrumbList)"[^<]*?</script>\s*',
        re.DOTALL
    )
    new_content, count = pattern.subn('', content)
    return new_content, count

def main():
    files = glob.glob(f"{ARTICLES_DIR}/*.md")
    total_removed = 0
    files_changed = 0

    for path in sorted(files):
        with open(path) as f:
            content = f.read()
        
        new_content, count = strip_schema_blocks(content)
        
        if count > 0:
            with open(path, 'w') as f:
                f.write(new_content)
            print(f"  {os.path.basename(path)}: removed {count} block(s)")
            total_removed += count
            files_changed += 1

    print(f"\nDone. {files_changed} files updated, {total_removed} schema blocks removed.")

if __name__ == "__main__":
    main()
