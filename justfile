run-flatpak: install-flatpak
  flatpak run land.arcana.TarotCanvas

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
  
  ${TEMP_DIR}/flatpak-pip-generator --yaml --checker-data --cleanup scripts requests toml xdg-base-dirs
  
  deactivate
  rm -rf "${TEMP_DIR}"
  
  mv python3-modules.yaml packaging

