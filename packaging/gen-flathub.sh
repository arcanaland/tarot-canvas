#!/bin/bash
# Generate the manifest Flathub builds: the production one, built from the
# release tarball instead of the source tree.
#
#   ./gen-flathub.sh TARBALL
set -euo pipefail

TARBALL="$(realpath "${1:?usage: gen-flathub.sh TARBALL}")"

cd "$(dirname "$0")"

PROD_ID="land.arcana.TarotCanvas"
OUT="flathub"
NAME="$(basename "${TARBALL}")"

mkdir -p "${OUT}"
rm -f "${OUT}/${PROD_ID}.yml"
[ "${TARBALL}" = "$(realpath "${OUT}")/${NAME}" ] || cp "${TARBALL}" "${OUT}/"

sed \
  -e "s|^  - python3-modules\.yaml\$|  - ../python3-modules.yaml|" \
  -e "s|^      - type: dir\$|      - type: archive|" \
  -e "s|^        path: \.\.\$|        path: ${NAME}|" \
  "${PROD_ID}.yml" >"${OUT}/${PROD_ID}.yml"

fail() {
  echo "gen-flathub.sh: $1" >&2
  exit 1
}

grep -q "^  - \.\./python3-modules\.yaml\$" "${OUT}/${PROD_ID}.yml" || fail "module path not rewritten"
grep -q "^      - type: archive\$" "${OUT}/${PROD_ID}.yml" || fail "source type not rewritten"
grep -qF "        path: ${NAME}" "${OUT}/${PROD_ID}.yml" || fail "source path not rewritten"

# Only the source may differ from what upstream builds
body() { sed '/^    sources:$/,$d' "$1"; }
[ "$(grep -c '^    sources:$' "${OUT}/${PROD_ID}.yml")" = 1 ] || fail "expected one sources: block"
diff <(body "${PROD_ID}.yml" | sed "s|^  - python3-modules\.yaml\$|  - ../python3-modules.yaml|") \
  <(body "${OUT}/${PROD_ID}.yml") || fail "the body above sources: differs from ${PROD_ID}.yml"

echo "generated packaging/${OUT}/${PROD_ID}.yml from ${NAME}"
