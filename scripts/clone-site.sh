#!/usr/bin/env bash
# Create a new site clone from this template.
#
# Usage:
#   scripts/clone-site.sh <site-slug> <template-repo-url> \
#     --brand="My Brand Name" \
#     --domain="mybrand.com" \
#     --amazon-tag="mybrand-20" \
#     [--domain-url="https://mybrand.com"]
#
# Example:
#   scripts/clone-site.sh four-season-cook git@github.com:yourname/fsg-template.git \
#     --brand="The Four Season Cook" \
#     --domain="four-season-cook.com" \
#     --amazon-tag="fourseasonc-20"
#
# All three flags (--brand, --domain, --amazon-tag) are REQUIRED.
# The script refuses to create a clone that would leak the template's identity.

set -e

# ── Parse arguments ───────────────────────────────────────────────────────────
SITE_SLUG="${1:?Usage: clone-site.sh <site-slug> <template-repo-url> --brand=... --domain=... --amazon-tag=...}"
TEMPLATE_URL="${2:?Usage: clone-site.sh <site-slug> <template-repo-url> --brand=... --domain=... --amazon-tag=...}"
shift 2

BRAND_NAME=""
DOMAIN=""
AMAZON_TAG=""

for arg in "$@"; do
  case "$arg" in
    --brand=*)   BRAND_NAME="${arg#*=}" ;;
    --domain=*)  DOMAIN="${arg#*=}" ;;
    --amazon-tag=*) AMAZON_TAG="${arg#*=}" ;;
  esac
done

if [ -z "$BRAND_NAME" ] || [ -z "$DOMAIN" ] || [ -z "$AMAZON_TAG" ]; then
  echo "Error: --brand, --domain, and --amazon-tag are all required." >&2
  echo "Example:" >&2
  echo "  clone-site.sh my-site git@github.com:you/template.git \\" >&2
  echo "    --brand=\"My Site Name\" --domain=\"mysite.com\" --amazon-tag=\"mysite-20\"" >&2
  exit 1
fi

TEMPLATE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="$(pwd)/$SITE_SLUG"

if [ -d "$TARGET_DIR" ]; then
  echo "Error: $TARGET_DIR already exists." >&2
  exit 1
fi

# ── Clone ─────────────────────────────────────────────────────────────────────
echo "Cloning template into $TARGET_DIR …"
git clone "$TEMPLATE_URL" "$TARGET_DIR"
cd "$TARGET_DIR"

# Rename origin → upstream so template changes can be pulled later
git remote rename origin upstream
echo "  remote 'upstream' → $TEMPLATE_URL"

# Configure the ours merge driver (keeps local version on git pull upstream)
git config merge.ours.driver true
echo "  merge.ours.driver configured"

# ── Substitute identity in site.config.yaml ───────────────────────────────────
SITE_YAML="site.config.yaml"
sed -i '' "s/brand_name: .*/brand_name: \"${BRAND_NAME}\"/" "$SITE_YAML"
sed -i '' "s/domain: \"fourseasongardener\.com\"/domain: \"${DOMAIN}\"/" "$SITE_YAML"
sed -i '' "s/amazon_tracking_id: .*/amazon_tracking_id: \"${AMAZON_TAG}\"/" "$SITE_YAML"
sed -i '' "s/ga4_measurement_id: .*/ga4_measurement_id: \"REPLACE_WITH_GA4_ID\"/" "$SITE_YAML"
echo "  site.config.yaml identity substituted"

# Substitute project name in wrangler.toml
sed -i '' "s/^name = \"four-season-gardener\"/name = \"${SITE_SLUG}\"/" wrangler.toml
echo "  wrangler.toml project name → $SITE_SLUG"

# Clear generated articles — each clone needs its own niche content
rm -f content/articles/*.md
echo "  content/articles/ cleared"

# ── Post-clone validation — fail closed on any template identity leak ─────────
echo ""
echo "Validating clone identity …"
LEAK=0

check_no_match() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if [ -f "$file" ] && grep -qE "$pattern" "$file"; then
    echo "  LEAK [$label] $file — still contains template value matching: $pattern" >&2
    LEAK=1
  fi
}

check_no_match "site.config.yaml"   "fourseasongardener\.com"   "domain"
check_no_match "site.config.yaml"   "Four Season Gardener"      "brand_name"
check_no_match "site.config.yaml"   "fourseasong-20"            "amazon_tag"
check_no_match "site.config.yaml"   "G-CTMQ2320CZ"             "ga4_id"
check_no_match "wrangler.toml"      "^name = \"four-season-gardener\"" "project_name"

if [ "$LEAK" -ne 0 ]; then
  echo "" >&2
  echo "Clone aborted — template identity still present. Fix the above before using this clone." >&2
  exit 1
fi

echo "  Identity clean — no template values detected."

# ── Register ──────────────────────────────────────────────────────────────────
CLONES_FILE="$TEMPLATE_DIR/scripts/clones.txt"
echo "$TARGET_DIR" >> "$CLONES_FILE"
echo "  registered in $CLONES_FILE"

SITES_FILE="$TEMPLATE_DIR/scripts/sites.txt"
echo "$DOMAIN" >> "$SITES_FILE"
echo "  domain '$DOMAIN' registered in $SITES_FILE"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "Clone ready at: $TARGET_DIR"
echo ""
echo "Remaining manual steps:"
echo "  1. Edit config/personas/*.yaml         — update persona name, bio, photo"
echo "  2. Replace public/images/brand/        — logo, OG image, author photo"
echo "  3. Replace content/products/products.yaml — niche products with real ASINs"
echo "  4. Replace data/pipeline.json          — niche article pipeline"
echo "  5. Set Cloudflare Pages env vars:"
echo "       AMAZON_TAG              — $AMAZON_TAG  (overrides site.config.yaml)"
echo "       GA4_ID                  — your GA4 measurement ID"
echo "       SITE_URL                — https://$DOMAIN"
echo "       GOOGLE_SITE_VERIFICATION — from Google Search Console (HTML tag method)"
echo "       BING_SITE_VERIFICATION   — from Bing Webmaster Tools (HTML tag method)"
echo "  6. git remote add origin <new-repo-url> && git push -u origin main"
echo ""
echo "To pull template updates later:"
echo "  cd $TARGET_DIR && git pull upstream main"
