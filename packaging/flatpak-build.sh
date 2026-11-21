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

# The MIME type is the same for both variants; the icons it names carry the variant's ID,
# because Flatpak exports only files named for the app.
MIME_XML="${FLATPAK_DEST}/share/mime/packages/${FLATPAK_ID}.xml"
mkdir -p "$(dirname "${MIME_XML}")"
sed -E "s/name=\"land\.arcana\.TarotCanvas([.\"])/name=\"${FLATPAK_ID}\1/g" \
  packaging/land.arcana.TarotCanvas.xml >"${MIME_XML}"
grep -qF "<icon name=\"${FLATPAK_ID}.tarotdeck\"/>" "${MIME_XML}" || {
  echo "flatpak-build.sh: ${MIME_XML} does not name ${FLATPAK_ID}.tarotdeck" >&2
  exit 1
}
for png in packaging/tarotdeck-icon/*.png; do
  size=$(basename "${png}" .png)
  install -Dm644 "${png}" "${FLATPAK_DEST}/share/icons/hicolor/${size}/mimetypes/${FLATPAK_ID}.tarotdeck.png"
done
