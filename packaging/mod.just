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

# Build, install and run the production-ID build.
run: install
  flatpak run land.arcana.TarotCanvas//master

gen-devel:
  ./gen-devel.sh

# Fast inner loop: run the devel build straight out of the build tree.
devel-run: devel-build
  flatpak run org.flatpak.Builder --run build-devel devel/land.arcana.TarotCanvas.yml tarot-canvas

# Build the devel build without installing it.
devel-build: gen-devel
  {{dbus}} flatpak run org.flatpak.Builder --user --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml

# Build and install the devel build
devel-install: gen-devel
  {{dbus}} flatpak run org.flatpak.Builder --user --install --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml

# Build, install and run the devel build.
devel: devel-install
  flatpak run land.arcana.TarotCanvas.Devel//master

devel-uninstall:
  flatpak uninstall --user -y land.arcana.TarotCanvas.Devel || true

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
