#!/bin/bash
# Generate the development-build manifest from the production one.
set -euo pipefail

cd "$(dirname "$0")"

PROD_ID="land.arcana.TarotCanvas"
DEVEL_ID="${PROD_ID}.Devel"
OUT="devel"

rm -rf "${OUT}"
mkdir -p "${OUT}"

sed \
  -e "s|^app-id: ${PROD_ID}\$|app-id: ${DEVEL_ID}|" \
  -e "s|packaging/${PROD_ID}\.desktop|packaging/${OUT}/${PROD_ID}.desktop|" \
  -e "s|packaging/${PROD_ID}\.appdata\.xml|packaging/${OUT}/${PROD_ID}.appdata.xml|" \
  -e "s|packaging/icon\.svg|packaging/${OUT}/icon.svg|" \
  -e "s|share/applications/${PROD_ID}\.desktop|share/applications/${DEVEL_ID}.desktop|" \
  -e "s|apps/${PROD_ID}\.svg|apps/${DEVEL_ID}.svg|" \
  -e "s|share/metainfo/${PROD_ID}\.metainfo\.xml|share/metainfo/${DEVEL_ID}.metainfo.xml|" \
  -e "s|^  - python3-modules\.yaml\$|  - ../python3-modules.yaml|" \
  -e "s|^        path: \.\.\$|        path: ../..|" \
  "${PROD_ID}.yml" >"${OUT}/${PROD_ID}.yml"

sed -e "s|^Icon=${PROD_ID}\$|Icon=${DEVEL_ID}|" \
  -e "s|^Name=Tarot Canvas\$|Name=Tarot Canvas (Devel)|" \
  -e "/^X-Flatpak-RenamedFrom=/d" \
  "${PROD_ID}.desktop" >"${OUT}/${PROD_ID}.desktop"

sed -e "s|<id>${PROD_ID}</id>|<id>${DEVEL_ID}</id>|" \
  -e "s|>${PROD_ID}\.desktop<|>${DEVEL_ID}.desktop<|" \
  -e "0,/<name>Tarot Canvas<\/name>/s||<name>Tarot Canvas (Devel)</name>|" \
  "${PROD_ID}.appdata.xml" >"${OUT}/${PROD_ID}.appdata.xml"

./gen-devel-icon.py icon.svg "${OUT}/icon.svg"

fail() {
  echo "gen-devel.sh: $1" >&2
  exit 1
}

grep -q "^app-id: ${DEVEL_ID}\$" "${OUT}/${PROD_ID}.yml" || fail "app-id not rewritten"
grep -q "^Icon=${DEVEL_ID}\$" "${OUT}/${PROD_ID}.desktop" || fail "desktop Icon= not rewritten"
grep -q "<id>${DEVEL_ID}</id>" "${OUT}/${PROD_ID}.appdata.xml" || fail "appdata <id> not rewritten"
grep -q "desktop-id\">${DEVEL_ID}\.desktop<" "${OUT}/${PROD_ID}.appdata.xml" || fail "appdata launchable not rewritten"
grep -q "<name>Tarot Canvas (Devel)</name>" "${OUT}/${PROD_ID}.appdata.xml" || fail "appdata <name> not rewritten"
grep -q "^  - \.\./python3-modules\.yaml\$" "${OUT}/${PROD_ID}.yml" || fail "module path not rewritten"
grep -q "^        path: \.\./\.\.\$" "${OUT}/${PROD_ID}.yml" || fail "source path not rewritten"
for d in "share/applications/${DEVEL_ID}.desktop" \
  "apps/${DEVEL_ID}.svg" \
  "share/metainfo/${DEVEL_ID}.metainfo.xml"; do
  grep -q "${d}\$" "${OUT}/${PROD_ID}.yml" || fail "install destination ${d} not rewritten"
done
for s in "packaging/${OUT}/${PROD_ID}.desktop" \
  "packaging/${OUT}/${PROD_ID}.appdata.xml" \
  "packaging/${OUT}/icon.svg"; do
  grep -q "install -Dm644 ${s} " "${OUT}/${PROD_ID}.yml" || fail "install source ${s} is wrong"
done
#
# No install destination should have the prod name
if grep -E "FLATPAK_DEST.*/${PROD_ID}\.(desktop|svg|metainfo\.xml)\$" "${OUT}/${PROD_ID}.yml"; then
  fail "a production ID survived in an install destination"
fi

echo "generated packaging/${OUT}/ for ${DEVEL_ID}"
