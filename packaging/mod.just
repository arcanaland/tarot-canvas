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

  RUNTIME_VERSION=$(grep "runtime-version:" land.arcana.TarotCanvas.yml | cut -d "'" -f 2)
  TEMP_DIR=$(mktemp -d)

  FLATPAK_PIP_GENERATOR_SHA=737c0085912f9f7dabf9341d4608e2a77a51a73a
  curl -L -o "${TEMP_DIR}/flatpak-pip-generator.py" \
    https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/${FLATPAK_PIP_GENERATOR_SHA}/pip/flatpak-pip-generator.py

  # PyYAML isn't in this script's PEP 723 metadata for some reason
  uv run --with PyYAML "${TEMP_DIR}/flatpak-pip-generator.py" \
    --yaml --checker-data --runtime=org.kde.Sdk//${RUNTIME_VERSION} \
    requests xdg-base-dirs tomli-w poetry-core

  rm -rf "${TEMP_DIR}"

  # remove poetry-core
  awk '
    /^  - name: / { in_poetry = ($3 == "python3-poetry-core") }
    in_poetry && /^    sources:$/ { print "    cleanup:"; print "      - \"*\""; in_poetry = 0; added = 1 }
    { print }
    END { exit !added }
  ' python3-modules.yaml >python3-modules.yaml.tmp \
    || { echo "gen-modules: poetry-core cleanup not added" >&2; exit 1; }
  mv python3-modules.yaml.tmp python3-modules.yaml

[private]
deps:
  #!/bin/bash
  set -euo pipefail

  RUNTIME_VERSION=$(grep "runtime-version:" land.arcana.TarotCanvas.yml | cut -d "'" -f 2)
  BASE_VERSION=$(grep "base-version:" land.arcana.TarotCanvas.yml | cut -d "'" -f 2)

  # Skip anything already installed, user or system, so this is cheap on every build
  missing=()
  for ref in \
    org.kde.Platform//${RUNTIME_VERSION} \
    org.kde.Sdk//${RUNTIME_VERSION} \
    com.riverbankcomputing.PyQt.BaseApp//${BASE_VERSION} \
    org.flatpak.Builder//stable; do
    flatpak info "$ref" >/dev/null 2>&1 || missing+=("$ref")
  done
  [ "${#missing[@]}" -gt 0 ] || exit 0

  # If you don't have this already, just add it because you should have it anyway ¯\_(ツ)_/¯
  flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

  echo "installing missing flatpak deps: ${missing[*]}"
  flatpak install --user -y --noninteractive flathub "${missing[@]}"

# Lint the manifest
lint-manifest: deps
  #!/bin/bash
  set -euo pipefail

  GHA=()
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    GHA=(--env=GITHUB_ACTIONS=true)
  fi

  {{dbus}} flatpak run "${GHA[@]}" --command=flatpak-builder-lint \
    org.flatpak.Builder --gha-format manifest land.arcana.TarotCanvas.yml

# Validate the AppStream metainfo.
validate: deps
  flatpak run --command=appstreamcli org.flatpak.Builder validate --no-net --explain ../tarot_canvas/resources/land.arcana.TarotCanvas.appdata.xml

build: deps
  {{dbus}} flatpak run org.flatpak.Builder --user --force-clean build-dir land.arcana.TarotCanvas.yml

install: deps
  {{dbus}} flatpak run org.flatpak.Builder --user --install --force-clean build-dir land.arcana.TarotCanvas.yml

# Build from the release tarball (match Flathub)
build-tarball: deps
  #!/bin/bash
  set -euo pipefail

  VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' ../tarot_canvas/_version.py)
  rm -rf flathub
  ../scripts/make-tarball.sh "${VERSION}" flathub
  ./gen-flathub.sh "flathub/tarot-canvas-${VERSION}.tar.gz"
  {{dbus}} flatpak run org.flatpak.Builder --user --force-clean \
    build-flathub flathub/land.arcana.TarotCanvas.yml

# Fast inner loop: run the devel build straight out of the build tree.
devel-run: devel-build
  flatpak run org.flatpak.Builder --run build-devel devel/land.arcana.TarotCanvas.yml tarot-canvas

# Build the devel build without installing it.
[private]
devel-build: deps gen-devel
  {{dbus}} flatpak run org.flatpak.Builder --user --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml

# Build and install the devel build
[private]
devel-install: deps gen-devel
  {{dbus}} flatpak run org.flatpak.Builder --user --install --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml

# Build, install and run the dev build.
devel: devel-install
  flatpak run land.arcana.TarotCanvas.Devel//master

# Build, install and run the dev build with a fresh config, data or both (all), kept
# until the next fresh run, the reference deck already in place.
devel-fresh WHAT="all": (fresh-what WHAT) devel-install (devel-in "fresh" WHAT "wipe" "seed")

# As devel-fresh, but a fresh data dir downloads the reference deck
devel-pristine WHAT="all": (fresh-what WHAT) devel-install (devel-in "pristine" WHAT "wipe")

# Build, install and run the dev build in a profile of its own, made empty if new
devel-as NAME: devel-install (devel-in NAME "all")

# Copy the dev build's config, data and cache into a new profile for devel-as
devel-snapshot NAME:
  #!/bin/bash
  set -euo pipefail

  root=~/.var/app/land.arcana.TarotCanvas.Devel
  profile="${root}/profiles/{{NAME}}"
  case "{{NAME}}" in
    fresh | pristine | */* | .* | "") echo "Not a profile name: {{NAME}}" >&2; exit 1 ;;
  esac
  if [ -e "${profile}" ]; then
    echo "Profile {{NAME}} already exists: ${profile}" >&2
    exit 1
  fi

  mkdir -p "${profile}"
  # Copy-on-write where the filesystem can, so a snapshot costs no space until it differs
  cp -a --reflink=auto "${root}/config" "${root}/data" "${root}/cache" "${profile}/"
  echo "Snapshot in ${profile}; run it with: just devel-as {{NAME}}"

# Before the build, so a typo doesn't wait for one
[private]
fresh-what WHAT:
  @case "{{WHAT}}" in config | data | all) ;; *) echo "Fresh what? config, data or all, not {{WHAT}}" >&2; exit 1 ;; esac

# Flatpak sets the XDG dirs after --env, so they are exported inside the sandbox
[private]
devel-in NAME WHAT WIPE="" SEED="":
  #!/bin/bash
  set -euo pipefail

  app=land.arcana.TarotCanvas.Devel
  root=~/.var/app/${app}
  profile="${root}/profiles/{{NAME}}"
  case "{{NAME}}" in
    */* | .* | "") echo "Not a profile name: {{NAME}}" >&2; exit 1 ;;
  esac
  case "{{WHAT}}" in
    config) parts=(config) ;;
    data) parts=(data) ;;
    all) parts=(config data cache) ;;
    *) echo "Fresh what? config, data or all, not {{WHAT}}" >&2; exit 1 ;;
  esac

  if [ -n "{{WIPE}}" ]; then
    rm -rf "${profile}"
  fi
  mkdir -p "${profile}/config" "${profile}/data" "${profile}/cache"
  # The host's KDE look and user dirs are mounted only into the default config dir
  for file in kdeglobals user-dirs.dirs; do
    ln -sfn "../../../config/${file}" "${profile}/config/${file}"
  done

  # The release zip the app downloads, kept on the host and named for its version
  if [ -n "{{SEED}}" ] && [[ " ${parts[*]} " == *" data "* ]]; then
    url=$(sed -n 's/^ *REFERENCE_DECK_URL = "\(.*\)"/\1/p' ../tarot_canvas/models/reference_deck.py)
    zip="${XDG_CACHE_HOME:-${HOME}/.cache}/tarot-canvas/reference-decks/$(basename "${url}")"
    if [ ! -f "${zip}" ]; then
      curl -fL --create-dirs -o "${zip}.part" "${url}"
      mv "${zip}.part" "${zip}"
    fi
    decks="${profile}/data/tarot-canvas/reference-decks"
    mkdir -p "${decks}"
    python3 -m zipfile -e "${zip}" "${decks}"
  fi

  exports=()
  for part in "${parts[@]}"; do
    exports+=("XDG_${part^^}_HOME=${profile}/${part}")
  done
  echo "Profile {{NAME}} (${parts[*]}): ${profile}"
  flatpak run --command=sh "${app}//master" -c 'export "$@"; exec tarot-canvas' sh "${exports[@]}"

# Uninstall dev build and delete its data
devel-uninstall:
  flatpak uninstall --user -y land.arcana.TarotCanvas.Devel || true
  rm -rf ~/.var/app/land.arcana.TarotCanvas.Devel/

# Check the Flathub app-listing quality guidelines that can be checked locally.
# Pass --remote to also print Flathub's live verdicts.
quality *ARGS:
  ../scripts/flathub_quality.py {{ARGS}}

# Resize the open app to a specific size and take a screenshot
shot NAME W='998' H='698':
  ../scripts/flathub_screenshot.py {{NAME}} {{W}} {{H}}

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
