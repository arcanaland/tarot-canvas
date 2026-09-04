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
  echo "  <add the <release> entry to packaging/land.arcana.TarotCanvas.appdata.xml>"
  echo "  just release-tag"
  echo "  just release-push"
  echo
  echo "The notes template is the XML comment at the top of <releases>."
  exit 1
