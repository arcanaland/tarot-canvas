generate-pip-modules:
  #!/bin/bash
  set -euo pipefail
  
  # Create a temporary directory
  TEMP_DIR=$(mktemp -d)
  
  # Create requirements file
  echo "toml>=0.10.2" > "${TEMP_DIR}/requirements.txt"
  echo "xdg>=5.1.1" >> "${TEMP_DIR}/requirements.txt"
  echo "requests>=2.31.0" >> "${TEMP_DIR}/requirements.txt"
  echo "xdg-base-dirs>=6.0.2" >> "${TEMP_DIR}/requirements.txt"
  
  # Create a temporary venv
  python3 -m venv "${TEMP_DIR}/venv"
  source "${TEMP_DIR}/venv/bin/activate"
  
  # Install requirements-parser
  pip install requirements-parser
  
  # Download flatpak-pip-generator if needed
  if ! command -v flatpak-pip-generator &> /dev/null; then
    echo "flatpak-pip-generator not found, downloading it..."
    curl -L -o "${TEMP_DIR}/flatpak-pip-generator" https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/pip/flatpak-pip-generator
    chmod +x "${TEMP_DIR}/flatpak-pip-generator"
    GENERATOR="${TEMP_DIR}/flatpak-pip-generator"
  else
    GENERATOR="flatpak-pip-generator"
  fi
  
  # Run flatpak-pip-generator with requirements file
  echo "Generating Python modules..."
  $GENERATOR --requirements-file="${TEMP_DIR}/requirements.txt" --output="python3-requirements" --runtime="org.kde.Platform//6.8"
  
  # Deactivate venv and clean up
  deactivate
  rm -rf "${TEMP_DIR}"
  
  echo "Python modules generated: python3-requirements.json"

build-flatpak:
  #!/bin/bash
  cd packaging
  flatpak-builder --force-clean build-dir land.arcana.TarotCanvas.yml

install-flatpak:
  #!/bin/bash
  cd packaging
  flatpak-builder --user --install --force-clean build-dir land.arcana.TarotCanvas.yml

run-flatpak:
  flatpak run land.arcana.TarotCanvas
