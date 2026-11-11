[private]
default:
  @just --list --list-submodules

mod flatpak 'packaging/mod.just'
mod bench 'bench/mod.just'

# Build+install+run in the flatpak
[group('dev')]
devel:
  @just flatpak devel

# Build+install+run in the flatpak with a fresh config, data or all
[group('dev')]
devel-fresh WHAT="all":
  @just flatpak devel-fresh {{WHAT}}

# As devel-fresh, but the reference deck is downloaded as on a first launch
[group('dev')]
devel-pristine WHAT="all":
  @just flatpak devel-pristine {{WHAT}}

# Build+install+run in the flatpak in a named profile
[group('dev')]
devel-as NAME:
  @just flatpak devel-as {{NAME}}

[group('dev')]
run:
  uv run tarot-canvas

[group('dev')]
test *ARGS:
  QT_QPA_PLATFORM=offscreen uv run pytest -n auto {{ARGS}}

# Run the suite under coverage
[group('dev')]
coverage *ARGS:
  QT_QPA_PLATFORM=offscreen UV_PROJECT_ENVIRONMENT=.venv-3.14 COVERAGE_FILE=.coverage.suite \
    uv run --python 3.14 pytest -n auto --cov --cov-report= {{ARGS}}
  @just _coverage-report

# Record a session of the real app under coverage
[group('dev')]
coverage-session:
  UV_PROJECT_ENVIRONMENT=.venv-3.14 COVERAGE_FILE=.coverage.session \
    uv run --python 3.14 coverage run -m tarot_canvas.main
  @just _coverage-report

[private]
_coverage-report:
  #!/bin/bash
  set -euo pipefail

  export UV_PROJECT_ENVIRONMENT=.venv-3.14
  data=()
  for f in .coverage.suite .coverage.session; do
    [ -f "$f" ] && data+=("$f")
  done
  [ "${#data[@]}" -gt 0 ] || { echo "no coverage data; run just coverage first" >&2; exit 1; }

  uv run --python 3.14 coverage combine --keep "${data[@]}"
  uv run --python 3.14 coverage html --keep-combined
  uv run --python 3.14 coverage json --keep-combined
  uv run --python 3.14 coverage report --keep-combined

[group('dev')]
lint:
  #!/bin/bash
  set -euo pipefail

  uv run ruff check tarot_canvas tests bench
  uv run ruff format --check tarot_canvas tests bench
  ./scripts/slop-guard.sh

# Refresh the bundled esoterica from a release, checked against its SHA256SUMS
[group('dev')]
esoterica-bundle TAG:
  #!/bin/bash
  set -euo pipefail

  base="https://github.com/arcanaland/esoterica/releases/download/{{TAG}}"
  files=(
    mcelroy-a-guide-to-tarot-card-meanings-2014.toml
    PROVENANCE.toml
    LicenseRef-McElroy-Uncopyright.txt
  )
  dest=tarot_canvas/resources/esoterica
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT

  for f in "${files[@]}" SHA256SUMS; do
    curl -fsSL -o "$tmp/$f" "$base/$f"
  done

  # Every bundled file must be listed, and match
  for f in "${files[@]}"; do
    sum="$(awk -v f="$f" '$2 == f { print $1 }' "$tmp/SHA256SUMS")"
    [ -n "$sum" ] || { echo "$f is not in SHA256SUMS" >&2; exit 1; }
    (cd "$tmp" && echo "$sum  $f" | sha256sum -c -)
  done

  mkdir -p "$dest"
  for f in "${files[@]}"; do
    cp "$tmp/$f" "$dest/"
  done

[group('dev')]
fmt:
  uv run ruff format tarot_canvas tests bench

# phase 1: bump the version but don't commit
[group('release')]
release-prepare VERSION="":
  ./scripts/release.sh prepare {{VERSION}}

# phase 2: commit the bump + tag
[group('release')]
release-tag:
  ./scripts/release.sh tag

# phase 3: push the branch and the tag atomically
[group('release')]
release-push:
  ./scripts/release.sh push

[group('release')]
release VERSION="":
  #!/bin/bash
  echo "Releasing is three phases:"
  echo
  echo "  just release-prepare {{VERSION}}"
  echo "  <add the <release> entry to tarot_canvas/resources/land.arcana.TarotCanvas.appdata.xml>"
  echo "  just release-tag"
  echo "  just release-push"
  echo
  echo "The notes template is the XML comment at the top of <releases>."
  exit 1
