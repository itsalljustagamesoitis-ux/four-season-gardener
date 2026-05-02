#!/usr/bin/env bash
# Pull latest template changes into all registered clones.
#
# Usage:
#   scripts/update-all-clones.sh [--dry-run]
#
# Clones are listed in scripts/clones.txt (one absolute path per line).
# Lines starting with # are ignored.
#
# Each clone must have:
#   - remote 'upstream' pointing to the template repo
#   - merge.ours.driver = true (clone-site.sh sets this automatically)
#
# On merge conflict: the clone is skipped and flagged. Site-specific files
# listed in .gitattributes are automatically kept (merge=ours driver).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLONES_FILE="$SCRIPT_DIR/clones.txt"
DRY_RUN=false
[ "$1" = "--dry-run" ] && DRY_RUN=true

if [ ! -f "$CLONES_FILE" ]; then
  echo "No clones registered. Run clone-site.sh to create one."
  exit 0
fi

TOTAL=0
UPDATED=0
SKIPPED=0
FAILED=0

while IFS= read -r clone_path || [ -n "$clone_path" ]; do
  # Skip blanks and comments
  [ -z "$clone_path" ] && continue
  [[ "$clone_path" =~ ^# ]] && continue

  TOTAL=$((TOTAL + 1))

  if [ ! -d "$clone_path" ]; then
    echo "SKIP  $clone_path — directory not found"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  if $DRY_RUN; then
    echo "DRY   $clone_path"
    continue
  fi

  echo "─── $clone_path"
  pushd "$clone_path" > /dev/null

  # Ensure merge driver is configured
  git config merge.ours.driver true

  # Fetch latest template
  git fetch upstream --quiet

  # Check if there's anything to merge
  LOCAL=$(git rev-parse HEAD)
  UPSTREAM=$(git rev-parse upstream/main)
  if [ "$LOCAL" = "$UPSTREAM" ]; then
    echo "  already up to date"
    popd > /dev/null
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  # Merge — site-specific files protected by .gitattributes merge=ours
  if git merge upstream/main --no-edit --quiet 2>&1; then
    git push --quiet
    echo "  updated + pushed"
    UPDATED=$((UPDATED + 1))
  else
    echo "  MERGE CONFLICT — resolve manually, then: git push"
    FAILED=$((FAILED + 1))
  fi

  popd > /dev/null

done < "$CLONES_FILE"

echo ""
echo "Done: $UPDATED updated, $SKIPPED skipped, $FAILED failed (of $TOTAL total)"
[ $FAILED -gt 0 ] && exit 1 || exit 0
