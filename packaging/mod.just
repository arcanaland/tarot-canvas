dbus := if env('DBUS_SESSION_BUS_ADDRESS', '') == '' { 'dbus-run-session --' } else { '' }

flathub_repo := 'flathub/land.arcana.TarotCanvas'

# Where the Flathub checkout lives. Not in this repo: it is a different repo with a
# different owner, and Flathub's copy of python3-modules.yaml is the canonical one.
flathub_checkout := env('FLATHUB_CHECKOUT', \
  env('XDG_CACHE_HOME', home_dir() / '.cache') / 'tarot-canvas' / 'flathub')

[private]
gen-devel:
  ./gen-devel.sh

[private]
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

[private]
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

# Fast inner loop: run the devel build straight out of the build tree.
devel-run: devel-build
  flatpak run org.flatpak.Builder --run build-devel devel/land.arcana.TarotCanvas.yml tarot-canvas

# Build the devel build without installing it.
[private]
devel-build: gen-devel
  {{dbus}} flatpak run org.flatpak.Builder --user --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml

# Build and install the devel build
[private]
devel-install: gen-devel
  {{dbus}} flatpak run org.flatpak.Builder --user --install --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml

# Build, install and run the dev build.
devel: devel-install
  flatpak run land.arcana.TarotCanvas.Devel//master

# Nuke the dev build and data and run
devel-pristine: devel-uninstall devel

# Uninstall dev build and delete its data
devel-uninstall:
  flatpak uninstall --user -y land.arcana.TarotCanvas.Devel || true
  rm -rf ~/.var/app/land.arcana.TarotCanvas.Devel/

# Check the Flathub app-listing quality guidelines that can be checked locally.
# Pass --remote to also print Flathub's live verdicts.
quality *ARGS:
  ../scripts/flathub_quality.py {{ARGS}}

# wipe installs from flathub build bot
[private]
buildbot-clean:
  #!/bin/bash
  set -euo pipefail

  for remote in $(flatpak remotes --user --columns=name,url | awk '$2 ~ /build-repo/ {print $1}'); do
    for ref in $(flatpak list --user --columns=application,origin,branch | awk -v r="$remote" '$2 == r {print $1"//"$3}'); do
      echo "uninstalling ${ref} (from ${remote})"
      flatpak uninstall --user -y "$ref"
    done
    if flatpak remotes --user --columns=name | grep -qx "$remote"; then
      echo "removing remote ${remote}"
      flatpak remote-delete --user --force "$remote"
    fi
  done

# install a flathub build
buildbot BUILD: buildbot-clean
  #!/bin/bash
  set -euo pipefail

  case "{{BUILD}}" in
    http*) URL="{{BUILD}}" ;;
    *)     URL="https://dl.flathub.org/build-repo/{{BUILD}}/land.arcana.TarotCanvas.flatpakref" ;;
  esac

  flatpak install --user -y "$URL"
  echo
  echo "run it with: flatpak run land.arcana.TarotCanvas//test"
 
# Open a Flathub PR
submit:
  #!/bin/bash
  set -euo pipefail

  CHECKOUT="{{flathub_checkout}}"
  VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' ../tarot_canvas/_version.py)
  BRANCH="update-${VERSION}"

  echo "== version:  ${VERSION}"
  echo "== checkout: ${CHECKOUT}"

  if [ -d "${CHECKOUT}/.git" ]; then
    git -C "${CHECKOUT}" fetch --quiet origin
  else
    mkdir -p "$(dirname "${CHECKOUT}")"
    git clone --quiet "https://github.com/{{flathub_repo}}.git" "${CHECKOUT}"
  fi

  git -C "${CHECKOUT}" config user.name "$(git config user.name)"
  git -C "${CHECKOUT}" config user.email "$(git config user.email)"

  git -C "${CHECKOUT}" checkout --quiet -B "${BRANCH}" origin/master

  podman run --rm \
    -v "${CHECKOUT}:/run/host/repo:Z" \
    -e GITHUB_TOKEN="$(gh auth token)" \
    ghcr.io/flathub-infra/flatpak-external-data-checker \
    --update --commit-only --commit-to-current-branch \
    /run/host/repo/land.arcana.TarotCanvas.yml

  if git -C "${CHECKOUT}" diff --quiet origin/master HEAD; then
    echo "== manifest already current for ${VERSION}; no PR opened"
    exit 0
  fi

  git -C "${CHECKOUT}" --no-pager log --oneline origin/master..HEAD
  git -C "${CHECKOUT}" push --quiet -u origin "${BRANCH}"

  gh pr create -R {{flathub_repo}} \
    --base master --head "${BRANCH}" \
    --title "Update tarot-canvas to ${VERSION}" \
    --body ''
