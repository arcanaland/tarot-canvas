mod flatpak 'packaging/mod.just'

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
