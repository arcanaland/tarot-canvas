# `dbus-run-session` spawns a private session bus, which activates a SECOND
# xdg-document-portal. That portal mounts over /run/user/$UID/doc and takes the
# mount down when the private session exits — leaving the real user service
# running but unmounted, so every flatpak on the machine then dies with
# "bwrap: Can't find source path /run/user/$UID/doc/by-app/...".
#
# Verified 2026-09-02: one build with dbus-run-session took the mount from 1 to 0
# and left the unit `failed`; the same build without it left the mount intact and
# succeeded. So spawn a bus only when there genuinely is not one, i.e. in CI.
dbus := if env('DBUS_SESSION_BUS_ADDRESS', '') == '' { 'dbus-run-session --' } else { '' }

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
  {{dbus}} flatpak run org.flatpak.Builder --user --force-clean build-dir land.arcana.TarotCanvas.yml

install:
  {{dbus}} flatpak run org.flatpak.Builder --user --install --force-clean build-dir land.arcana.TarotCanvas.yml

run: install
  flatpak run land.arcana.TarotCanvas//master

# --- development build (ADR-014) -------------------------------------------
# The devel build carries its own app ID, so it gets its own ~/.var/app tree,
# desktop entry and icon, and installs side by side with production.

# Regenerate packaging/devel/ from the production manifest.
gen-devel:
  ./gen-devel.sh

# --run applies build-time permissions, NOT the manifest's finish-args. Anything
# depending on the real sandbox — the reference-deck download behind --share=network,
# portal access, --device=dri — must be tested with `devel-install` or it proves
# nothing. Note --run takes the command positionally after the manifest, and must not
# be combined with --force-clean, which would wipe the tree being run from.

# Fast inner loop: run the devel build straight out of the build tree.
devel-run: devel-build
  flatpak run org.flatpak.Builder --run build-devel devel/land.arcana.TarotCanvas.yml tarot-canvas

# Build the devel build without installing it.
devel-build: gen-devel
  {{dbus}} flatpak run org.flatpak.Builder --user --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml

# Build and install the devel build, side by side with production.
devel-install: gen-devel
  {{dbus}} flatpak run org.flatpak.Builder --user --install --force-clean \
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
