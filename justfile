run-flatpak: install-flatpak
  flatpak run land.arcana.TarotCanvas

run:
  poetry run tarot-canvas

install-flatpak:
  #!/bin/bash
  cd packaging
  flatpak-builder --user --install --force-clean build-dir land.arcana.TarotCanvas.yml

build-flatpak:
  #!/bin/bash
  cd packaging
  flatpak-builder --force-clean build-dir land.arcana.TarotCanvas.yml

generate-flatpak-python3-modules:
  #!/bin/bash
  set -exuo pipefail
  
  TEMP_DIR=$(mktemp -d)
  
  # Create a temporary venv
  python3 -m venv "${TEMP_DIR}/venv"
  source "${TEMP_DIR}/venv/bin/activate"
  
  pip install requirements-parser PyYAML
  

  curl -L -o "${TEMP_DIR}/flatpak-pip-generator" https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/pip/flatpak-pip-generator
  chmod +x "${TEMP_DIR}/flatpak-pip-generator"
  
  ${TEMP_DIR}/flatpak-pip-generator --yaml --checker-data --cleanup scripts requests tomli xdg-base-dirs
  
  deactivate
  rm -rf "${TEMP_DIR}"
  
  mv python3-modules.yaml packaging

release VERSION="":
  #!/bin/bash
  set -e

  # Colors for output
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  NC='\033[0m' # No Color
  
  echo -e "${GREEN}Tarot Canvas Release Helper${NC}"
  echo "==============================="
  
  # Get current version
  CURRENT_VERSION=$(poetry version -s)
  echo -e "Current version: ${YELLOW}$CURRENT_VERSION${NC}"

  # Use provided version or ask for new one
  if [ -z "{{VERSION}}" ]; then
    echo -n "Enter new version (or press Enter to keep current): "
    read NEW_VERSION
    if [ -z "$NEW_VERSION" ]; then
      NEW_VERSION=$CURRENT_VERSION
    fi
  else
    NEW_VERSION="{{VERSION}}"
  fi

  echo -e "Target version: ${YELLOW}$NEW_VERSION${NC}"

  # Update version if different
  if [ "$NEW_VERSION" != "$CURRENT_VERSION" ]; then
    echo "Updating version..."
    poetry version $NEW_VERSION
    
    # Update version in _version.py
    sed -i "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" tarot_canvas/_version.py
    
    echo -e "${GREEN}Version updated to $NEW_VERSION${NC}"
  fi

  # Check if git is clean
  if [ -n "$(git status --porcelain)" ]; then
    echo -e "${YELLOW}Warning: Working directory is not clean${NC}"
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
    echo "Committing version changes..."
    git add pyproject.toml tarot_canvas/_version.py
    git commit -m "chore: bump version to $NEW_VERSION"
  fi

  # Create and push tag
  TAG_NAME="v$NEW_VERSION"
  echo "Creating tag: $TAG_NAME"

  if git tag -l | grep -q "^$TAG_NAME$"; then
    echo -e "${RED}Tag $TAG_NAME already exists!${NC}"
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
  echo "Next steps:"
  echo "1. Push the tag to trigger the GitHub Action:"
  echo -e "   ${YELLOW}git push origin main"
  echo -e "   ${YELLOW}git push origin $TAG_NAME${NC}"

