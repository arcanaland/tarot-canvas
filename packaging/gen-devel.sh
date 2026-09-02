#!/bin/bash
# Generate the development-build manifest from the production one.
#
# Nothing here is checked in: a second hand-maintained manifest is exactly the
# drift failure RFC-010 §3 recorded for land.arcana.TarotCanvas.flathub.yml. The
# derived files cannot go stale because they are regenerated on every build.
#
# Output lands in packaging/devel/, so the manifest's `path:` source becomes ../..
# (the repo root) and the install commands address packaging/devel/*.
set -euo pipefail

cd "$(dirname "$0")"

PROD_ID="land.arcana.TarotCanvas"
DEVEL_ID="${PROD_ID}.Devel"
OUT="devel"

rm -rf "${OUT}"
mkdir -p "${OUT}"

# Source paths and install destinations are rewritten separately and anchored:
# an unanchored s|/<id>.desktop| matches the source path first.
sed \
  -e "s|^app-id: ${PROD_ID}\$|app-id: ${DEVEL_ID}|" \
  -e "s|packaging/${PROD_ID}\.desktop|packaging/${OUT}/${PROD_ID}.desktop|" \
  -e "s|packaging/${PROD_ID}\.appdata\.xml|packaging/${OUT}/${PROD_ID}.appdata.xml|" \
  -e "s|share/applications/${PROD_ID}\.desktop|share/applications/${DEVEL_ID}.desktop|" \
  -e "s|apps/${PROD_ID}\.svg|apps/${DEVEL_ID}.svg|" \
  -e "s|share/metainfo/${PROD_ID}\.metainfo\.xml|share/metainfo/${DEVEL_ID}.metainfo.xml|" \
  -e "s|^  - python3-modules\.yaml\$|  - ../python3-modules.yaml|" \
  -e "s|^        path: \.\.\$|        path: ../..|" \
  "${PROD_ID}.yml" > "${OUT}/${PROD_ID}.yml"

sed -e "s|^Icon=${PROD_ID}\$|Icon=${DEVEL_ID}|" \
    -e "s|^Name=Tarot Canvas\$|Name=Tarot Canvas (Devel)|" \
    -e "/^X-Flatpak-RenamedFrom=/d" \
    "${PROD_ID}.desktop" > "${OUT}/${PROD_ID}.desktop"

sed -e "s|<id>${PROD_ID}</id>|<id>${DEVEL_ID}</id>|" \
    -e "s|>${PROD_ID}\.desktop<|>${DEVEL_ID}.desktop<|" \
    -e "0,/<name>Tarot Canvas<\/name>/s||<name>Tarot Canvas (Devel)</name>|" \
    "${PROD_ID}.appdata.xml" > "${OUT}/${PROD_ID}.appdata.xml"

# A sed that silently matches nothing yields a build with a mismatched ID — the
# failure mode this script is most likely to have. Assert rather than hope.
fail() { echo "gen-devel.sh: $1" >&2; exit 1; }

grep -q "^app-id: ${DEVEL_ID}\$" "${OUT}/${PROD_ID}.yml"        || fail "app-id not rewritten"
grep -q "^Icon=${DEVEL_ID}\$"    "${OUT}/${PROD_ID}.desktop"    || fail "desktop Icon= not rewritten"
grep -q "<id>${DEVEL_ID}</id>"   "${OUT}/${PROD_ID}.appdata.xml" || fail "appdata <id> not rewritten"
grep -q "desktop-id\">${DEVEL_ID}\.desktop<" "${OUT}/${PROD_ID}.appdata.xml" || fail "appdata launchable not rewritten"
grep -q "<name>Tarot Canvas (Devel)</name>"    "${OUT}/${PROD_ID}.appdata.xml" || fail "appdata <name> not rewritten"
grep -q "^  - \.\./python3-modules\.yaml\$"  "${OUT}/${PROD_ID}.yml" || fail "module path not rewritten"
grep -q "^        path: \.\./\.\.\$"         "${OUT}/${PROD_ID}.yml" || fail "source path not rewritten"
for d in "share/applications/${DEVEL_ID}.desktop" \
         "apps/${DEVEL_ID}.svg" \
         "share/metainfo/${DEVEL_ID}.metainfo.xml"; do
  grep -q "${d}\$" "${OUT}/${PROD_ID}.yml" || fail "install destination ${d} not rewritten"
done
for s in "packaging/${OUT}/${PROD_ID}.desktop" \
         "packaging/${OUT}/${PROD_ID}.appdata.xml" \
         "packaging/icon.svg"; do
  grep -q "install -Dm644 ${s} " "${OUT}/${PROD_ID}.yml" || fail "install source ${s} is wrong"
done
# No install *destination* may still carry the bare production ID.
if grep -E "FLATPAK_DEST.*/${PROD_ID}\.(desktop|svg|metainfo\.xml)\$" "${OUT}/${PROD_ID}.yml"; then
  fail "a production ID survived in an install destination"
fi

echo "generated packaging/${OUT}/ for ${DEVEL_ID}"
