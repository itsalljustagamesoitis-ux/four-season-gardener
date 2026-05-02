#!/usr/bin/env bash
# Create a new site clone from this template.
#
# Usage:
#   scripts/clone-site.sh <site-slug> <template-repo-url> [domain]
#
# Example:
#   scripts/clone-site.sh four-season-cook git@github.com:yourname/fsg-template.git four-season-cook.com
#
# What it does:
#   1. Clones the template repo into ./<site-slug>/
#   2. Renames origin → upstream so template fixes can be pulled later
#   3. Configures the "ours" merge driver to protect site-specific files
#   4. Clears article content (products.yaml and persona need manual customisation)
#   5. Registers the new clone in scripts/clones.txt of THIS repo

set -e

SITE_SLUG="${1:?Usage: clone-site.sh <site-slug> <template-repo-url> [domain]}"
TEMPLATE_URL="${2:?Usage: clone-site.sh <site-slug> <template-repo-url> [domain]}"
DOMAIN="${3:-}"
TEMPLATE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="$(pwd)/$SITE_SLUG"

if [ -d "$TARGET_DIR" ]; then
  echo "Error: $TARGET_DIR already exists." >&2
  exit 1
fi

echo "Cloning template into $TARGET_DIR …"
git clone "$TEMPLATE_URL" "$TARGET_DIR"
cd "$TARGET_DIR"

# Rename origin → upstream so template changes can be pulled
git remote rename origin upstream
echo "  remote 'upstream' → $TEMPLATE_URL"

# Configure the ours merge driver (keeps local version on git pull upstream)
git config merge.ours.driver true
echo "  merge.ours.driver configured"

# Clear generated articles — each clone needs its own niche content
rm -f content/articles/*.md
echo "  content/articles/ cleared (add niche articles here)"

# Register this clone in the template's clones.txt
CLONES_FILE="$TEMPLATE_DIR/scripts/clones.txt"
echo "$TARGET_DIR" >> "$CLONES_FILE"
echo "  registered in $CLONES_FILE"

# Register domain in sites.txt for health monitoring
SITES_FILE="$TEMPLATE_DIR/scripts/sites.txt"
if [ -n "$DOMAIN" ]; then
  echo "$DOMAIN" >> "$SITES_FILE"
  echo "  domain '$DOMAIN' registered in $SITES_FILE"
else
  echo "  (no domain provided — add it to scripts/sites.txt manually for health monitoring)"
fi

echo ""
echo "Clone ready at: $TARGET_DIR"
echo ""
echo "Next steps:"
echo "  1. Edit site.config.yaml         — brand_name, domain, amazon_tracking_id"
echo "  2. Edit config/personas/*.yaml   — rename persona, update bio"
echo "  3. Replace public/images/brand/  — logo, OG image, author photo"
echo "  4. Replace content/products/products.yaml — niche products"
echo "  5. Replace data/pipeline.json    — niche article pipeline"
echo "  6. Set Cloudflare Pages env vars: AMAZON_TAG, GA4_ID"
echo "  7. git remote add origin <new-repo-url> && git push -u origin main"
echo ""
echo "To pull template updates later:"
echo "  cd $TARGET_DIR && git pull upstream main"
