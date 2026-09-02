# `just --list` does not recurse into modules, so the flatpak recipes are invisible
# to it. Bare `just` lists everything; keep this recipe first so it stays the default.
[private]
default:
  @just --list --list-submodules

# Flatpak packaging and dev builds. `just --list flatpak` to see them all.
mod flatpak 'packaging/mod.just'

# Surfaced at the root because it is the one flatpak recipe worth finding without
# a flag; the rest live in the module.

# Build, install and run the development build, side by side with production.
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

[group('release')]
release VERSION="":
  ./scripts/release.sh {{VERSION}}
