#!/usr/bin/env python3
"""Take a store screenshot of Tarot Canvas at a fixed window size (KDE Plasma 6 only).

KWin resizes and focuses the app's window, Spectacle captures it with its shadow,
and the result is checked against the requested size before it is saved.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from flathub_quality import APP_ID, MAX_SHOT, SHOTS, window_size

SCRIPT_NAME = "tarot-canvas-shot"

# Matches both the release build and the Devel one (`land.arcana.TarotCanvas.Devel`).
RESIZE_JS = """
for (const w of workspace.windowList()) {{
  if (!w.normalWindow || !w.resourceClass.startsWith("{app_id}")) continue;
  w.setMaximize(false, false);
  const g = w.frameGeometry;
  w.frameGeometry = {{x: g.x, y: g.y, width: {width}, height: {height}}};
  workspace.activeWindow = w;
  break;
}}
"""


def kwin(*args: str) -> str:
    return subprocess.run(
        ["busctl", "--user", "call", "org.kde.KWin", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def unload() -> None:
    kwin("/Scripting", "org.kde.kwin.Scripting", "unloadScript", "s", SCRIPT_NAME)


def resize_and_focus(width: int, height: int, tmp: Path) -> None:
    js = tmp / "resize.js"
    js.write_text(RESIZE_JS.format(app_id=APP_ID, width=width, height=height))
    unload()  # a crashed earlier run leaves the name taken
    # busctl prints the returned int as "i <id>"
    script_id = kwin(
        "/Scripting", "org.kde.kwin.Scripting", "loadScript", "ss", str(js), SCRIPT_NAME
    ).split()[1]
    kwin(f"/Scripting/Script{script_id}", "org.kde.kwin.Script", "run")


def capture(png: Path) -> None:
    subprocess.run(
        [
            "spectacle",
            "--activewindow",
            "--background",
            "--nonotify",
            "--delay",
            "500",
            "--output",
            str(png),
        ],
        check=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("name", help="saved as packaging/screenshots/NAME.webp")
    ap.add_argument("width", type=int, help="window frame width, logical px, title bar included")
    ap.add_argument("height", type=int, help="window frame height, logical px")
    args = ap.parse_args()

    from PIL import Image

    out = SHOTS / f"{args.name}.webp"
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        png = tmp / "shot.png"
        try:
            resize_and_focus(args.width, args.height, tmp)
            capture(png)
        finally:
            unload()

        w, h = window_size(png)
        scale = w / args.width
        if abs(h / args.height - scale) > 0.01:
            print(
                f"captured a {w}x{h} window, not {args.width}x{args.height} at any scale: "
                "is Tarot Canvas open?",
                file=sys.stderr,
            )
            return 1
        im = Image.open(png)
        im.save(out, quality=90)

    print(
        f"{out.relative_to(SHOTS.parent.parent)}: window {w}x{h} at {scale:.2f}x, "
        f"file {im.size[0]}x{im.size[1]}"
    )
    if w > MAX_SHOT[0] or h > MAX_SHOT[1]:
        print(f"warning: window is over Flathub's {MAX_SHOT[0]}x{MAX_SHOT[1]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
