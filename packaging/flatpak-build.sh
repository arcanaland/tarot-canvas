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

pip3 install --no-deps --no-build-isolation --prefix="${FLATPAK_DEST}" .
install -Dm644 "${DESKTOP}" -t "${FLATPAK_DEST}/share/applications/"
install -Dm644 "${ICON}" -t "${FLATPAK_DEST}/share/icons/hicolor/scalable/apps/"
install -Dm644 "${METAINFO}" -t "${FLATPAK_DEST}/share/metainfo/"
