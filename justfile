[private]
default:
  @just --list --list-submodules

mod flatpak 'packaging/mod.just'

# Build+install+run in the flatpak
[group('dev')]
devel:
  @just flatpak devel

[group('dev')]
run:
  uv run tarot-canvas

[group('dev')]
test *ARGS:
  QT_QPA_PLATFORM=offscreen uv run pytest {{ARGS}}

[group('dev')]
lint:
  #!/bin/bash
  set -euo pipefail

  uv run ruff check tarot_canvas tests
  uv run ruff format --check tarot_canvas tests
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
  uv run ruff format tarot_canvas tests

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
