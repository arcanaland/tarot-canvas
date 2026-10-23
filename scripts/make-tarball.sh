#!/usr/bin/env bash
# Build the release source tarball
#
#   ./scripts/make-tarball.sh VERSION OUTDIR

set -euo pipefail

VERSION="${1:?usage: make-tarball.sh VERSION OUTDIR}"
OUTDIR="${2:?usage: make-tarball.sh VERSION OUTDIR}"
mkdir -p "${OUTDIR}"
OUTDIR="$(realpath "${OUTDIR}")"

cd "$(dirname "$0")/.."

# DO NOT RENAME. The asset name is part of the Flathub manifest's x-checker-data.
NAME="tarot-canvas-${VERSION}"
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

mkdir -p "${STAGE}/${NAME}"
git ls-files -z --cached --others --exclude-standard tarot_canvas packaging pyproject.toml uv.lock README.md LICENSE |
  xargs -0 cp --parents -t "${STAGE}/${NAME}"

tar -czf "${OUTDIR}/${NAME}.tar.gz" -C "${STAGE}" "${NAME}"
(cd "${OUTDIR}" && sha256sum "${NAME}.tar.gz" >"${NAME}.tar.gz.sha256")
