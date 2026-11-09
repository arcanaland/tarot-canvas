#!/usr/bin/env python3
"""Check Flathub app-listing quality guidelines"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
METAINFO = REPO / "tarot_canvas" / "resources" / "land.arcana.TarotCanvas.appdata.xml"
ICON = REPO / "packaging" / "icon.png"
SHOTS = REPO / "packaging" / "screenshots"
APP_ID = "land.arcana.TarotCanvas"

API = "https://flathub.org/api/v2/quality-moderation/{app_id}"

MAX_SHOT = (2000, 1400)
# Alpha at or above which a screenshot pixel is window, not shadow.
SHOT_OPAQUE = 250
FOOTPRINT_MAX = 0.90
FOOTPRINT_MIN = 0.60
# "Dark colors near the edges are a problem since shadows don't help on dark backgrounds."
EDGE_DARK_MAX = 0.50

GENERIC_NOUNS = {"app", "application", "tool", "client", "utility", "program", "software"}
ARTICLES = {"a", "an", "the"}


@dataclass
class Result:
    guideline: str
    ok: bool
    detail: str


def _text(root: ET.Element, path: str) -> str:
    """Text of the first untranslated match, whitespace-collapsed."""
    for el in root.findall(path):
        if el.get("{http://www.w3.org/XML/1998/namespace}lang"):
            continue
        return re.sub(r"\s+", " ", (el.text or "")).strip()
    return ""


def check_name(root: ET.Element) -> list[Result]:
    name = _text(root, "name")
    return [
        Result(
            "app-name-not-too-long",
            len(name) < 20,
            f"{len(name)} chars (must be <20, ideally <=15): {name!r}",
        )
    ]


def check_summary(root: ET.Element) -> list[Result]:
    s = _text(root, "summary")
    words = re.findall(r"[\w'-]+", s.lower())
    name = _text(root, "name").lower()
    generic = sorted(GENERIC_NOUNS.intersection(words))
    out = [
        Result(
            "app-summary-not-too-long",
            len(s) <= 35,
            f"{len(s)} chars (must be <=35, ideally 10-25): {s!r}",
        ),
        # heuristic stand-in
        Result(
            "app-summary-not-technical",
            not generic,
            f"generic nouns: {generic}" if generic else "no generic nouns",
        ),
        Result(
            "app-summary-no-weird-formatting",
            not s.endswith("."),
            "ends with a full stop" if s.endswith(".") else "ok",
        ),
        Result(
            "app-summary-dont-repeat-app-name",
            name not in s.lower(),
            f"repeats the app name {name!r}" if name in s.lower() else "ok",
        ),
        Result(
            "app-summary-dont-start-with-an-article",
            not words or words[0] not in ARTICLES,
            f"starts with {words[0]!r}" if words and words[0] in ARTICLES else "ok",
        ),
    ]
    return out


def check_branding(root: ET.Element) -> list[Result]:
    colors = {
        c.get("scheme_preference"): (c.text or "").strip()
        for c in root.findall("branding/color")
        if c.get("type") == "primary"
    }
    light, dark = colors.get("light"), colors.get("dark")
    has_both = bool(light and dark)
    res = [
        Result(
            "branding-has-primary-brand-colors",
            has_both,
            f"light={light} dark={dark}" if has_both else "no <branding> primary colors",
        )
    ]
    if has_both:

        def lum(hex_: str) -> float:
            h = hex_.lstrip("#")
            r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
            return 0.299 * r + 0.587 * g + 0.114 * b

        problems = []
        if light.lower() == dark.lower():
            problems.append("light and dark are the same color")
        if lum(light) < lum(dark):
            problems.append("the dark variant is lighter than the light variant")
        for label, value in (("light", light), ("dark", dark)):
            if lum(value) > 240:
                problems.append(f"{label} is near-white")
            if lum(value) < 20:
                problems.append(f"{label} is near-black")
        res.append(
            Result(
                "branding-good-primary-brand-colors",
                not problems,
                "; ".join(problems) if problems else "distinct, colorful",
            )
        )
    return res


def check_releases(root: ET.Element) -> list[Result]:
    missing = [
        r.get("version", "?")
        for r in root.findall("releases/release")
        if r.find("description") is None
    ]
    return [
        Result(
            "release-notes-for-every-release",
            not missing,
            f"no release notes for {missing}" if missing else "all releases have notes",
        )
    ]


def check_description(root: ET.Element) -> list[Result]:
    items = root.findall("description/ul/li")
    return [
        Result(
            "description-no-super-long-lists",
            len(items) <= 10,
            f"{len(items)} bullet points (max 10)",
        )
    ]


def window_size(path: Path) -> tuple[int, int]:
    """The window's size in a screenshot, without its shadow.

    The guideline limits the window and requires its shadow, so the file is
    larger than the window by the shadow. The shadow is translucent and the
    window opaque, so the window is the bounding box of the opaque pixels.
    """
    from PIL import Image

    im = Image.open(path)
    if "A" not in im.getbands():
        return im.size
    box = im.getchannel("A").point(lambda a: 255 if a >= SHOT_OPAQUE else 0).getbbox()
    return (box[2] - box[0], box[3] - box[1]) if box else im.size


def check_screenshots(root: ET.Element) -> list[Result]:
    shots = root.findall("screenshots/screenshot")
    no_caption = [
        s.findtext("image", "?") for s in shots if not (s.findtext("caption") or "").strip()
    ]
    res = [
        Result("screenshots-at-least-one-screenshot", bool(shots), f"{len(shots)} screenshots"),
        Result(
            "screenshots-image-captions",
            not no_caption,
            f"{len(no_caption)} without a caption" if no_caption else "all captioned",
        ),
    ]
    try:
        import PIL  # noqa: F401
    except ImportError:
        res.append(
            Result("screenshots-reasonable-window-size", True, "SKIPPED: Pillow not installed")
        )
        return res
    oversized = []
    for path in sorted(SHOTS.glob("*.webp")):
        w, h = window_size(path)
        if w > MAX_SHOT[0] or h > MAX_SHOT[1]:
            oversized.append(f"{path.name} {w}x{h}")
    res.append(
        Result(
            "screenshots-reasonable-window-size",
            not oversized,
            (
                f"window max is {MAX_SHOT[0]}x{MAX_SHOT[1]} (HiDPI), shadow excluded; over: "
                + ", ".join(oversized)
                if oversized
                else f"all windows within {MAX_SHOT[0]}x{MAX_SHOT[1]}, shadow excluded"
            ),
        )
    )
    return res


def check_icon() -> list[Result]:
    try:
        from PIL import Image
    except ImportError:
        return [Result("app-icon-*", True, "SKIPPED: Pillow not installed")]

    im = Image.open(ICON).convert("RGBA")
    w, h = im.size
    bbox = im.getchannel("A").getbbox() or (0, 0, w, h)
    fw, fh = (bbox[2] - bbox[0]) / w, (bbox[3] - bbox[1]) / h
    footprint = max(fw, fh)

    px = im.load()
    ring = dark = 0
    for x in range(w):
        for y in range(h):
            r, g, b, a = px[x, y]
            if a < 128:
                continue
            dx, dy = (x - w / 2) / (w / 2), (y - h / 2) / (h / 2)
            if dx * dx + dy * dy > 0.82:  # outer ~10% of the canvas radius
                ring += 1
                if 0.299 * r + 0.587 * g + 0.114 * b < 80:
                    dark += 1
    dark_frac = dark / ring if ring else 0.0

    return [
        Result(
            "app-icon-size",
            w == h and w >= 256,
            f"{w}x{h} (must be square, >=256)",
        ),
        Result(
            "app-icon-footprint",
            FOOTPRINT_MIN <= footprint <= FOOTPRINT_MAX,
            f"opaque content spans {fw:.0%}x{fh:.0%} of the canvas "
            f"(want {FOOTPRINT_MIN:.0%}-{FOOTPRINT_MAX:.0%})",
        ),
        Result(
            "app-icon-contrast",
            dark_frac <= EDGE_DARK_MAX,
            f"{dark_frac:.0%} of the outer ring is very dark "
            f"(want <={EDGE_DARK_MAX:.0%}); dark edges vanish on dark backgrounds",
        ),
    ]


def remote_status() -> None:
    with urllib.request.urlopen(API.format(app_id=APP_ID), timeout=30) as r:
        data = json.load(r)
    buckets: dict[str, list[str]] = {"FAIL": [], "UNREVIEWED": [], "PASS": []}
    for g in data["guidelines"]:
        key = {False: "FAIL", None: "UNREVIEWED", True: "PASS"}[g["passed"]]
        kind = "auto " if g["guideline"]["read_only"] else "human"
        buckets[key].append(f"    [{kind}] {g['guideline_id']}")
    print(f"\nFlathub's live verdicts for {APP_ID}:")
    for key in ("FAIL", "UNREVIEWED", "PASS"):
        print(f"  {key} ({len(buckets[key])})")
        print("\n".join(buckets[key]))
    print(f"\n  review_requested_at: {data['review_requested_at']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--remote", action="store_true", help="also print Flathub's live verdicts")
    args = ap.parse_args()

    root = ET.parse(METAINFO).getroot()
    results = [
        *check_name(root),
        *check_summary(root),
        *check_branding(root),
        *check_description(root),
        *check_releases(root),
        *check_screenshots(root),
        *check_icon(),
    ]

    width = max(len(r.guideline) for r in results)
    failed = 0
    for r in results:
        if not r.ok:
            failed += 1
        print(f"  {'PASS' if r.ok else 'FAIL'}  {r.guideline:<{width}}  {r.detail}")
    print(f"\n{len(results) - failed}/{len(results)} local checks pass.")

    if args.remote:
        remote_status()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
