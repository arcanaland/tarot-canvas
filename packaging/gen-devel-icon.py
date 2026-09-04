#!/usr/bin/env python3
"""Create the black and yellow under construction icon"""

import re
import sys

BACK_DISC_ID = "circle1"
STRIPE_DARK = "#000000"
STRIPE_LIGHT = "#fff600"
PERIOD = 100  # stripe pitch in user units
DUTY = 0.5  # dark fraction of each period
ANGLE = 45


def find_element(svg, element_id):
    marker = svg.find(f'id="{element_id}"')
    if marker == -1:
        raise SystemExit(f"gen-devel-icon.py: no element with id={element_id!r}")
    start = svg.rfind("<", 0, marker)
    end = svg.find(">", marker) + 1
    return start, end


def own_rotation(element):
    m = re.search(r'transform="[^"]*rotate\(\s*(-?[\d.]+)', element)
    return float(m.group(1)) if m else 0.0


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)

    src, dst = sys.argv[1], sys.argv[2]

    with open(src, encoding="utf-8") as fh:
        svg = fh.read()

    # 1. Repaint the back
    start, end = find_element(svg, BACK_DISC_ID)
    element = svg[start:end]
    repainted, n = re.subn(r'fill="[^"]*"', 'fill="url(#hazard)"', element, count=1)

    if n == 0:
        raise SystemExit(f"gen-devel-icon.py: {BACK_DISC_ID} has no fill attribute")

    svg = svg[:start] + repainted + svg[end:]

    # 2. Inject pattern after the root <svg>
    angle = ANGLE - own_rotation(element)
    pattern = (
        f'<defs id="defs-devel"><pattern id="hazard" width="{PERIOD}"'
        f' height="{PERIOD}" patternUnits="userSpaceOnUse"'
        f' patternTransform="rotate({angle:.4g})">'
        f'<rect width="{PERIOD}" height="{PERIOD}" fill="{STRIPE_LIGHT}"/>'
        f'<rect width="{PERIOD * DUTY:.4g}" height="{PERIOD}" fill="{STRIPE_DARK}"/>'
        f"</pattern></defs>"
    )
    root = re.search(r"<svg\b[^>]*>", svg)
    if root is None:
        raise SystemExit("gen-devel-icon.py: no <svg> root element")
    svg = svg[: root.end()] + pattern + svg[root.end() :]

    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"generated {dst}")


if __name__ == "__main__":
    main()
