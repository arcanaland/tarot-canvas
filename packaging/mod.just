deps:
  #!/bin/bash
  set -euo pipefail

  RUNTIME_VERSION=$(grep "runtime-version:" land.arcana.TarotCanvas.yml | cut -d "'" -f 2)
  BASE_VERSION=$(grep "base-version:" land.arcana.TarotCanvas.yml | cut -d "'" -f 2)

  # If you don't have this already, just add it because you should have it anyway ¯\_(ツ)_/¯
  flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

  flatpak install --user -y --noninteractive flathub \
    org.kde.Platform//${RUNTIME_VERSION} \
    org.kde.Sdk//${RUNTIME_VERSION} \
    com.riverbankcomputing.PyQt.BaseApp//${BASE_VERSION} \
    org.flatpak.Builder

# Validate the AppStream metainfo.
validate:
  flatpak run --command=appstreamcli org.flatpak.Builder validate --explain land.arcana.TarotCanvas.appdata.xml

build:
  dbus-run-session -- flatpak run org.flatpak.Builder --user --force-clean build-dir land.arcana.TarotCanvas.yml

install:
  dbus-run-session -- flatpak run org.flatpak.Builder --user --install --force-clean build-dir land.arcana.TarotCanvas.yml

# Pinned to //master so the ref is never resolved by chance when a second branch
# (e.g. a Flathub test build) is installed.

# Build, install and run the production-ID build.
run: install
  flatpak run land.arcana.TarotCanvas//master

# --- development build (RFC-012) -------------------------------------------
# The devel build carries its own app ID, so it gets its own ~/.var/app tree,
# desktop entry and icon, and installs side by side with production.

# Regenerate packaging/devel/ from the production manifest.
gen-devel:
  ./gen-devel.sh

# No repo export, no branch, no entry in `flatpak list`, nothing to confuse with
# an installed build.
#
# NOTE: --run applies build-time permissions, NOT the manifest's finish-args.
# Anything that depends on the real sandbox — the reference-deck download behind
# --share=network, portal access, --device=dri — must be tested via `devel-install`
# or the test proves nothing.

# Fast inner loop: run the devel build straight out of the build tree.
devel-run: gen-devel
  dbus-run-session -- flatpak run org.flatpak.Builder --user --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml --run tarot-canvas

# Build the devel build without installing it.
devel-build: gen-devel
  dbus-run-session -- flatpak run org.flatpak.Builder --user --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml

# Build and install the devel build, side by side with production.
devel-install: gen-devel
  dbus-run-session -- flatpak run org.flatpak.Builder --user --install --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml

# Build, install and run the devel build.
devel: devel-install
  flatpak run land.arcana.TarotCanvas.Devel//master

# Remove the installed devel build.
devel-uninstall:
  flatpak uninstall --user -y land.arcana.TarotCanvas.Devel || true

# Exercises the first-launch path, including the reference-deck download.

# Wipe the devel build's state, leaving production's untouched.
devel-reset:
  rm -rf ~/.var/app/land.arcana.TarotCanvas.Devel

gen-modules:
  #!/bin/bash
  set -euo pipefail

  TEMP_DIR=$(mktemp -d)

  FLATPAK_PIP_GENERATOR_SHA=737c0085912f9f7dabf9341d4608e2a77a51a73a
  curl -L -o "${TEMP_DIR}/flatpak-pip-generator.py" \
    https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/${FLATPAK_PIP_GENERATOR_SHA}/pip/flatpak-pip-generator.py

  # PyYAML isn't in this script's PEP 723 metadata for some reason
  uv run --with PyYAML "${TEMP_DIR}/flatpak-pip-generator.py" \
    --yaml --checker-data --cleanup scripts requests xdg-base-dirs poetry-core

  rm -rf "${TEMP_DIR}"
