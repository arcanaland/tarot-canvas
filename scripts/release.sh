#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

CURRENT_VERSION=$(uv version --short)
echo -e "== current version: ${YELLOW}$CURRENT_VERSION${NC}"

# Use provided version or ask for new one
if [ -z "${1:-}" ]; then
  echo -n "Enter new version (or press Enter to keep current): "
  read NEW_VERSION
  if [ -z "$NEW_VERSION" ]; then
    NEW_VERSION=$CURRENT_VERSION
  fi
else
  NEW_VERSION="${1:-}"
fi

echo -e "== target version: ${YELLOW}$NEW_VERSION${NC}"

# Update version if different
if [ "$NEW_VERSION" != "$CURRENT_VERSION" ]; then
  echo "Updating version..."
  uv version $NEW_VERSION

  # Update version in _version.py
  sed -i "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" tarot_canvas/_version.py

  echo -e "${GREEN}== version updated to $NEW_VERSION${NC}"
fi

# Update AppStream metadata with new release
RELEASE_DATE=$(date +%Y-%m-%d)
echo "Updating AppStream metadata..."
echo -n "Enter release description (or press Enter for default): "
read RELEASE_DESC
if [ -z "$RELEASE_DESC" ]; then
  RELEASE_DESC="Release version $NEW_VERSION"
fi

# Create new release entry using awk to insert after <releases>
awk -v version="$NEW_VERSION" -v date="$RELEASE_DATE" -v desc="$RELEASE_DESC" '
  /<releases>/ {
    print
    print "    <release version=\"" version "\" date=\"" date "\" type=\"stable\">"
    print "      <description>"
    print "        <p>" desc "</p>"
    print "      </description>"
    print "    </release>"
    next
  }
  { print }
' packaging/land.arcana.TarotCanvas.appdata.xml >packaging/land.arcana.TarotCanvas.appdata.xml.tmp

mv packaging/land.arcana.TarotCanvas.appdata.xml.tmp packaging/land.arcana.TarotCanvas.appdata.xml

echo -e "${GREEN}AppStream metadata updated${NC}"

# Check if git is clean
if [ -n "$(git status --porcelain)" ]; then
  echo -e "${YELLOW}== warning: Working directory is not clean${NC}"
  echo "The following files have changes:"
  git status --short
  echo -n "Continue anyway? (y/N): "
  read CONTINUE
  if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
    echo "Aborted."
    exit 1
  fi
fi

# Commit version changes if any
if [ -n "$(git diff --cached)" ] || [ -n "$(git diff)" ]; then
  echo "== committing version changes..."
  git add pyproject.toml tarot_canvas/_version.py packaging/land.arcana.TarotCanvas.appdata.xml
  git commit -m "chore: bump version to $NEW_VERSION"
fi

# Create and push tag
TAG_NAME="v$NEW_VERSION"
echo "== creating tag: $TAG_NAME"

if git tag -l | grep -q "^$TAG_NAME$"; then
  echo -e "${RED} == tag $TAG_NAME already exists!${NC}"
  echo -n "Delete existing tag and recreate? (y/N): "
  read DELETE_TAG
  if [ "$DELETE_TAG" = "y" ] || [ "$DELETE_TAG" = "Y" ]; then
    git tag -d $TAG_NAME
    git push origin :refs/tags/$TAG_NAME 2>/dev/null || true
  else
    echo "Aborted."
    exit 1
  fi
fi

git tag -a $TAG_NAME -m "Release $NEW_VERSION"

echo -e "${GREEN}Tag created successfully!${NC}"
echo ""
echo "Next step is to push:"
echo -e "   ${YELLOW}git push origin main"
echo -e "   ${YELLOW}git push origin $TAG_NAME${NC}"
