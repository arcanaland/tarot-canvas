#!/bin/bash
set -euo pipefail

case "${FLATPAK_ID}" in
land.arcana.TarotCanvas)
  DESKTOP="packaging/${FLATPAK_ID}.desktop"
  ICON="packaging/icon.svg"
  METAINFO="tarot_canvas/resources/${FLATPAK_ID}.appdata.xml"
  ;;
land.arcana.TarotCanvas.Devel)
  DESKTOP="packaging/devel/${FLATPAK_ID}.desktop"
  ICON="packaging/devel/icon.svg"
  METAINFO="packaging/devel/${FLATPAK_ID}.appdata.xml"
  ;;
*)
  echo "flatpak-build.sh: unknown FLATPAK_ID '${FLATPAK_ID}'" >&2
  exit 1
  ;;
esac

pip3 install --no-index --no-build-isolation --prefix="${FLATPAK_DEST}" .
install -Dm644 "${DESKTOP}" -t "${FLATPAK_DEST}/share/applications/"
install -Dm644 "${ICON}" -t "${FLATPAK_DEST}/share/icons/hicolor/scalable/apps/"
install -Dm644 "${METAINFO}" -t "${FLATPAK_DEST}/share/metainfo/"

# MIME type stuff
MIME_XML="${FLATPAK_DEST}/share/mime/packages/${FLATPAK_ID}.xml"
mkdir -p "$(dirname "${MIME_XML}")"
sed -E "s/name=\"land\.arcana\.TarotCanvas([.\"])/name=\"${FLATPAK_ID}\1/g" \
  packaging/land.arcana.TarotCanvas.xml >"${MIME_XML}"
grep -qF "<icon name=\"${FLATPAK_ID}.tarotdeck\"/>" "${MIME_XML}" || {
  echo "flatpak-build.sh: ${MIME_XML} does not name ${FLATPAK_ID}.tarotdeck" >&2
  exit 1
}
install -Dm644 packaging/tarotdeck-icon.svg \
  "${FLATPAK_DEST}/share/icons/hicolor/scalable/mimetypes/${FLATPAK_ID}.tarotdeck.svg"
