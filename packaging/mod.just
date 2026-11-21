dbus := if env('DBUS_SESSION_BUS_ADDRESS', '') == '' { 'dbus-run-session --' } else { '' }

flathub_repo := 'flathub/land.arcana.TarotCanvas'

# What devel-install last installed: its inputs' fingerprint and the installed commit
devel_stamp := env('XDG_CACHE_HOME', home_dir() / '.cache') / 'tarot-canvas' / 'devel-installed'

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

  # Versions come from uv.lock, which uv export first updates if pyproject.toml moved.
  # PyQt is the BaseApp's.
  uv export --quiet --no-dev --no-emit-project --no-hashes \
    --no-emit-package pyqt6 --no-emit-package pyqt6-qt6 --no-emit-package pyqt6-sip \
    --output-file "${TEMP_DIR}/requirements.txt"
  # The generator can't evaluate these markers, so it would vendor the wrong thing
  if grep -nE ';.*(python_(full_)?version|platform_machine)' "${TEMP_DIR}/requirements.txt" >&2; then
    echo "gen-modules: requirements carry markers flatpak-pip-generator can't evaluate" >&2
    exit 1
  fi
  # A build requirement, so not in the lock
  echo poetry-core >>"${TEMP_DIR}/requirements.txt"

  # PyYAML isn't in this script's PEP 723 metadata for some reason
  uv run --with PyYAML "${TEMP_DIR}/flatpak-pip-generator.py" \
    --yaml --checker-data --runtime=org.kde.Sdk//${RUNTIME_VERSION} \
    --prefer-wheels=arcana-tarot \
    --requirements-file="${TEMP_DIR}/requirements.txt" -o python3-modules
  sed -i "1s|${TEMP_DIR}/||" python3-modules.yaml

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

  # Unpin the install lines, so a wheel the external data checker bumps still installs
  sed -i -E 's/^( +--prefix=\$\{FLATPAK_DEST\} "[^"=]+)==[^"]*"/\1"/' python3-modules.yaml
  if grep -nE '^ +--prefix=.*"[^"]*==' python3-modules.yaml >&2; then
    echo "gen-modules: a pip3 install line is still pinned" >&2
    exit 1
  fi

  # A dependency pinned to one version moves only with a release, which submit carries,
  # so the checker must leave it alone
  for dist in $(./pinned-deps.py ../pyproject.toml); do
    awk -v module="python3-${dist}" '
      /^  - name: / { inmod = ($3 == module) }
      inmod && /^        x-checker-data:$/ { skip = 1; removed = 1; next }
      skip && /^          / { next }
      { skip = 0; print }
      END { exit !removed }
    ' python3-modules.yaml >python3-modules.yaml.tmp \
      || { echo "gen-modules: no checker data removed from python3-${dist}" >&2; exit 1; }
    mv python3-modules.yaml.tmp python3-modules.yaml
  done

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

# Import every tarot_canvas module inside the build
smoke dir='build-flathub': deps
  flatpak build --runtime {{dir}} python3 -B -c "import importlib, pkgutil, tarot_canvas; mods = [importlib.import_module(m.name) for m in pkgutil.walk_packages(tarot_canvas.__path__, 'tarot_canvas.')]; print(f'imported {len(mods)} tarot_canvas modules')"

# Fast inner loop: run the devel build straight out of the build tree.
devel-run: devel-build
  flatpak run org.flatpak.Builder --run build-devel devel/land.arcana.TarotCanvas.yml tarot-canvas

# Build the devel build without installing it.
[private]
devel-build: deps gen-devel
  {{dbus}} flatpak run org.flatpak.Builder --user --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml

# Build and install the devel build, whether or not anything changed
devel-install: deps gen-devel
  {{dbus}} flatpak run org.flatpak.Builder --user --install --force-clean \
    build-devel devel/land.arcana.TarotCanvas.yml
  @mkdir -p "$(dirname {{devel_stamp}})"
  @echo "$({{just_executable()}} --justfile {{justfile()}} devel-fingerprint) $({{just_executable()}} --justfile {{justfile()}} devel-commit)" >{{devel_stamp}}

# Build and install the devel build only if its inputs or the installed build changed
[private]
devel-ensure:
  #!/bin/bash
  set -euo pipefail
  now="$({{just_executable()}} --justfile {{justfile()}} devel-fingerprint) $({{just_executable()}} --justfile {{justfile()}} devel-commit)"
  if [ -f {{devel_stamp}} ] && [ "$(cat {{devel_stamp}})" = "${now}" ]; then
    echo "devel build is current; just devel-install to rebuild anyway"
    exit 0
  fi
  {{just_executable()}} --justfile {{justfile()}} devel-install

# What goes into the devel build: every file git doesn't ignore, by path and content
[private]
devel-fingerprint:
  #!/bin/bash
  set -euo pipefail
  cd ..
  git ls-files -co --exclude-standard -z -- tarot_canvas packaging pyproject.toml uv.lock README.md \
    | while IFS= read -r -d '' file; do [ -f "${file}" ] && printf '%s\0' "${file}"; done \
    | xargs -0 --no-run-if-empty sha256sum | sha256sum | cut -d ' ' -f 1

# The installed devel build's commit, or "none"
[private]
devel-commit:
  @flatpak info --user --show-commit land.arcana.TarotCanvas.Devel//master 2>/dev/null || echo none

# Build, install and run the dev build.
devel: devel-ensure
  flatpak run land.arcana.TarotCanvas.Devel//master

# Build, install and run the dev build with a fresh config, data or both (all), kept
# until the next fresh run, the reference deck already in place.
devel-fresh WHAT="all": (fresh-what WHAT) devel-ensure (devel-in "fresh" WHAT "wipe" "seed")

# As devel-fresh, but a fresh data dir downloads the reference deck
devel-pristine WHAT="all": (fresh-what WHAT) devel-ensure (devel-in "pristine" WHAT "wipe")

# Build, install and run the dev build in a profile of its own, made empty if new
devel-as NAME: devel-ensure (devel-in NAME "all")

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

# Calculate install/update stats from Flathub
stats *ARGS:
  ../scripts/flathub_stats.py {{ARGS}}

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
 
# Compare with Flathub's manifest
drift ref='master':
  #!/bin/bash
  set -uo pipefail

  api="repos/{{flathub_repo}}/contents"
  if ! flathub_manifest=$(gh api "${api}/land.arcana.TarotCanvas.yml?ref={{ref}}" \
      -H 'Accept: application/vnd.github.raw' 2>/dev/null) \
    || ! flathub_modules=$(gh api "${api}/python3-modules.yaml?ref={{ref}}" \
      -H 'Accept: application/vnd.github.raw' 2>/dev/null); then
    echo "drift: could not reach Flathub"
    exit 0
  fi

  if body=$(diff -u --label "flathub/{{ref}}" --label "upstream (working tree)" \
      <(./manifest-body.sh <(printf '%s\n' "${flathub_manifest}")) \
      <(./manifest-body.sh land.arcana.TarotCanvas.yml)); then
    echo "drift: none"
  else
    echo "drift: submit will carry this"
    printf '%s\n' "${body}"
  fi

  flathub_deps=$(./module-deps.sh <(printf '%s\n' "${flathub_modules}"))
  upstream_deps=$(./module-deps.sh python3-modules.yaml)
  missing=$(comm -13 <(printf '%s\n' "${flathub_deps}") <(printf '%s\n' "${upstream_deps}") | xargs)
  extra=$(comm -23 <(printf '%s\n' "${flathub_deps}") <(printf '%s\n' "${upstream_deps}") | xargs)
  if [ -z "${missing}${extra}" ]; then
    echo "deps: none"
  fi
  [ -z "${missing}" ] || echo "deps: missing on Flathub: ${missing}"
  [ -z "${extra}" ] || echo "deps: only on Flathub: ${extra}"
  exit 0

# Open a Flathub PR for the tagged version. --dry-run stops before pushing.
submit *FLAGS:
  #!/bin/bash
  set -euo pipefail

  DRY_RUN=
  for flag in {{FLAGS}}; do
    case "${flag}" in
      --dry-run) DRY_RUN=1 ;;
      *) echo "submit: unknown flag ${flag}" >&2; exit 1 ;;
    esac
  done

  die() { echo "== $1" >&2; exit 1; }

  CHECKOUT="{{flathub_checkout}}"
  MANIFEST=land.arcana.TarotCanvas.yml
  MODULES=python3-modules.yaml
  VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' ../tarot_canvas/_version.py)
  TAG="v${VERSION}"
  BRANCH="update-${VERSION}"
  REPO=$(git rev-parse --show-toplevel)
  WORK=$(mktemp -d)
  trap 'rm -rf "${WORK}"' EXIT

  echo "== version:  ${VERSION}"
  echo "== checkout: ${CHECKOUT}"

  # The body comes from the tag, so an unreleased edit on main can't leak
  git -C "${REPO}" rev-parse --verify --quiet "refs/tags/${TAG}" >/dev/null \
    || die "no local tag ${TAG}"
  git -C "${REPO}" show "${TAG}:packaging/${MANIFEST}" >"${WORK}/tagged.yml"
  ./manifest-body.sh "${WORK}/tagged.yml" >"${WORK}/tagged-body"

  if [ -d "${CHECKOUT}/.git" ]; then
    git -C "${CHECKOUT}" fetch --quiet origin
  else
    mkdir -p "$(dirname "${CHECKOUT}")"
    git clone --quiet "https://github.com/{{flathub_repo}}.git" "${CHECKOUT}"
  fi

  git -C "${CHECKOUT}" config user.name "$(git config user.name)"
  git -C "${CHECKOUT}" config user.email "$(git config user.email)"

  git -C "${CHECKOUT}" checkout --quiet -B "${BRANCH}" origin/master

  # Flathub's body must be one upstream has had since the version Flathub ships.
  # If not, someone edited Flathub directly: port that edit upstream first.
  ./manifest-body.sh "${CHECKOUT}/${MANIFEST}" >"${WORK}/flathub-body"
  OLD=$(sed -n 's|.*/download/v\([^/]*\)/.*|\1|p' "${CHECKOUT}/${MANIFEST}" | head -1)
  [ -n "${OLD}" ] || die "no /download/vX.Y.Z/ in Flathub's url:"
  git -C "${REPO}" rev-parse --verify --quiet "refs/tags/v${OLD}" >/dev/null \
    || die "no local tag v${OLD}, the version Flathub ships"
  matched=
  for rev in "v${OLD}" $(git -C "${REPO}" log --format=%h "v${OLD}..${TAG}" -- "packaging/${MANIFEST}"); do
    if git -C "${REPO}" show "${rev}:packaging/${MANIFEST}" | ./manifest-body.sh /dev/stdin 2>/dev/null \
        | cmp -s - "${WORK}/flathub-body"; then
      matched="${rev}"
      break
    fi
  done
  if [ -z "${matched}" ]; then
    diff -u --label "upstream ${TAG}" --label "flathub master" \
      "${WORK}/tagged-body" "${WORK}/flathub-body" || true
    die "Flathub's manifest body matches no upstream revision since v${OLD}.
     It was edited on Flathub. Port the edit upstream, tag, then submit."
  fi
  echo "== Flathub's body is upstream's at ${matched}"

  # Upstream's body at the tag, then Flathub's sources: block and everything below
  { cat "${WORK}/tagged-body"; sed -n '/^    sources:$/,$p' "${CHECKOUT}/${MANIFEST}"; } >"${WORK}/spliced.yml"
  # Nothing above sources: may differ from the tag
  lines=$(($(wc -l <"${WORK}/tagged-body") + 1))
  cmp -s <(head -n "${lines}" "${WORK}/spliced.yml") <(head -n "${lines}" "${WORK}/tagged.yml") \
    || die "the spliced manifest differs from ${TAG}'s above sources:"
  if ! cmp -s "${WORK}/spliced.yml" "${CHECKOUT}/${MANIFEST}"; then
    cp "${WORK}/spliced.yml" "${CHECKOUT}/${MANIFEST}"
    git -C "${CHECKOUT}" commit --quiet -m "Update manifest body from upstream ${TAG}" -- "${MANIFEST}"
    echo "== manifest body updated from ${TAG}"
  fi

  # A dependency the tag pins to one version moves only with a release, and the
  # checker leaves it alone: take its module from the tag, as for the body
  git -C "${REPO}" show "${TAG}:packaging/${MODULES}" >"${WORK}/tagged-modules.yaml"
  git -C "${REPO}" show "${TAG}:pyproject.toml" >"${WORK}/pyproject.toml"
  for dist in $(./pinned-deps.py "${WORK}/pyproject.toml"); do
    ./module-deps.sh --blocks "${WORK}/tagged-modules.yaml" "${dist}" >"${WORK}/pinned-block"
    module=$(sed -n 's/^  - name: //p' "${WORK}/pinned-block" | head -1)
    # Not in the tag's modules (the BaseApp's PyQt), or not on Flathub yet: the
    # missing-dependency check below handles the second
    [ -n "${module}" ] || continue
    awk -v module="${module}" -v block="${WORK}/pinned-block" '
      /^  - name: / {
        skip = ($3 == module)
        if (skip && !done) { while ((getline line <block) > 0) print line; done = 1 }
      }
      !skip { print }
    ' "${CHECKOUT}/${MODULES}" >"${WORK}/modules.yaml"
    if ! cmp -s "${WORK}/modules.yaml" "${CHECKOUT}/${MODULES}"; then
      cp "${WORK}/modules.yaml" "${CHECKOUT}/${MODULES}"
      git -C "${CHECKOUT}" commit --quiet -m "Update ${module} from upstream ${TAG}" -- "${MODULES}"
      echo "== ${module} updated from ${TAG}"
    fi
  done

  # A dry run reports a checker failure and goes on, so it still shows everything else
  if ! podman run --rm \
      -v "${CHECKOUT}:/run/host/repo:Z" \
      -e GITHUB_TOKEN="$(gh auth token)" \
      ghcr.io/flathub-infra/flatpak-external-data-checker \
      --update --commit-only --commit-to-current-branch \
      /run/host/repo/${MANIFEST}; then
    [ -n "${DRY_RUN}" ] || die "the external data checker failed (above)"
    echo "== the external data checker failed (above); a real submit stops here"
  fi

  if [ -n "${DRY_RUN}" ]; then
    git -C "${CHECKOUT}" --no-pager log -p origin/master..HEAD
  fi

  # The checker bumps only the modules Flathub already lists, so a new dependency
  # never arrives on its own.
  flathub_deps=$(./module-deps.sh "${CHECKOUT}/${MODULES}")
  tagged_deps=$(./module-deps.sh "${WORK}/tagged-modules.yaml")
  extra=$(comm -23 <(printf '%s\n' "${flathub_deps}") <(printf '%s\n' "${tagged_deps}") | xargs)
  missing=$(comm -13 <(printf '%s\n' "${flathub_deps}") <(printf '%s\n' "${tagged_deps}") | xargs)
  [ -z "${extra}" ] || echo "== note: only on Flathub (dropped upstream): ${extra}"
  if [ -n "${missing}" ]; then
    echo "== missing on Flathub: ${missing}"
    echo "== ${TAG}'s ${MODULES} carries them in:"
    # shellcheck disable=SC2086
    ./module-deps.sh --blocks "${WORK}/tagged-modules.yaml" ${missing}
    die "port these modules into Flathub's ${MODULES} by hand, then submit again. Nothing was pushed."
  fi

  # A pinned install line can't install the wheel the checker just bumped
  if grep -nE '^ +--prefix=.*"[^"]*==' "${CHECKOUT}/${MODULES}" >&2; then
    die "Flathub's ${MODULES} pins the install lines above. Unpin them by hand
     (gen-modules writes them unpinned), then submit again. Nothing was pushed."
  fi

  if [ -z "${DRY_RUN}" ]; then
    if git -C "${CHECKOUT}" diff --quiet origin/master HEAD; then
      echo "== manifest already current for ${VERSION}; no PR opened"
    else
      git -C "${CHECKOUT}" --no-pager log --oneline origin/master..HEAD
      git -C "${CHECKOUT}" push --quiet -u origin "${BRANCH}"

      gh pr create -R {{flathub_repo}} \
        --base master --head "${BRANCH}" \
        --title "Update tarot-canvas to ${VERSION}" \
        --body ''
    fi
  else
    echo "== dry run: nothing pushed"
  fi

  # check for bot PRs
  if ! bots=$(gh pr list -R {{flathub_repo}} --author flathubbot --state open \
      --json number,title --jq '.[] | "\(.number)\t\(.title)"'); then
    echo "== note: could not list bot PRs on {{flathub_repo}}"
  elif [ -n "${bots}" ]; then
    echo "== open bot PRs, superseded by this submit:"
    while IFS=$'\t' read -r number title; do
      echo "   #${number} ${title}"
      echo "   gh pr close ${number} -R {{flathub_repo}} --comment 'Superseded by the release PR.'"
    done <<<"${bots}"
  fi
