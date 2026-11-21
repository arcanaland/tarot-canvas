#!/usr/bin/env python3
"""Render the house back as the .tarotdeck file icon, one PNG per size

usage: uv run packaging/gen-mime-icons.py

Writes packaging/tarotdeck-icon/<N>x<N>.png, which are committed; flatpak-build.sh
installs them under each variant's own icon name. Rerun when the house back changes.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QGuiApplication  # noqa: E402

from tarot_canvas.ui.house_back import FILE_ICON_SIZES, file_icon  # noqa: E402

OUT = Path(__file__).resolve().parent / "tarotdeck-icon"


def main():
    if len(sys.argv) != 1:
        raise SystemExit(__doc__)
    app = QGuiApplication([])  # noqa: F841 -- QImage text and painting need one
    OUT.mkdir(exist_ok=True)
    for size in FILE_ICON_SIZES:
        path = OUT / f"{size}x{size}.png"
        if not file_icon(size).save(str(path)):
            raise SystemExit(f"gen-mime-icons.py: could not write {path}")
    print(f"wrote {len(FILE_ICON_SIZES)} icons to packaging/{OUT.name}/")


if __name__ == "__main__":
    main()
