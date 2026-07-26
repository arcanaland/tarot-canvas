set shell := ["bash", "-euo", "pipefail", "-c"]

deps:
  RUNTIME_VERSION=$(grep "runtime-version:" land.arcana.TarotCanvas.yml | cut -d "'" -f 2)
  BASE_VERSION=$(grep "base-version:" land.arcana.TarotCanvas.yml | cut -d "'" -f 2)

  # If you don't have this already, just add it because you should have it anyway ¯\_(ツ)_/¯
  flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

  flatpak install --user -y --noninteractive flathub \
    org.kde.Platform//${RUNTIME_VERSION} \
    org.kde.Sdk//${RUNTIME_VERSION} \
    com.riverbankcomputing.PyQt.BaseApp//${BASE_VERSION} \
    org.flatpak.Builder

build:
  dbus-run-session -- flatpak run org.flatpak.Builder --user --force-clean build-dir land.arcana.TarotCanvas.yml

install:
  dbus-run-session -- flatpak run org.flatpak.Builder --user --install --force-clean build-dir land.arcana.TarotCanvas.yml

run: install
  flatpak run land.arcana.TarotCanvas

gen-modules:
  TEMP_DIR=$(mktemp -d)

  # Create a temporary venv
  python3 -m venv "${TEMP_DIR}/venv"
  source "${TEMP_DIR}/venv/bin/activate"

  pip install requirements-parser PyYAML

  FLATPAK_PIP_GENERATOR_SHA=737c0085912f9f7dabf9341d4608e2a77a51a73a
  curl -L -o "${TEMP_DIR}/flatpak-pip-generator" https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/${FLATPAK_PIP_GENERATOR_SHA}/pip/flatpak-pip-generator.py
  chmod +x "${TEMP_DIR}/flatpak-pip-generator"

  ${TEMP_DIR}/flatpak-pip-generator --yaml --checker-data --cleanup scripts requests xdg-base-dirs poetry-core

  deactivate
  rm -rf "${TEMP_DIR}"
