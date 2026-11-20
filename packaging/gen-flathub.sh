#!/bin/bash
# Generate the Flathub manifest
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
upstream_body=$(./manifest-body.sh "${PROD_ID}.yml") || fail "no body in ${PROD_ID}.yml"
generated_body=$(./manifest-body.sh "${OUT}/${PROD_ID}.yml") || fail "no body in ${OUT}/${PROD_ID}.yml"
diff <(printf '%s\n' "${upstream_body}" | sed "s|^  - python3-modules\.yaml\$|  - ../python3-modules.yaml|") \
  <(printf '%s\n' "${generated_body}") || fail "the body above sources: differs from ${PROD_ID}.yml"

echo "generated packaging/${OUT}/${PROD_ID}.yml from ${NAME}"
