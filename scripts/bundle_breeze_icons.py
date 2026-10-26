#!/usr/bin/env python3
"""Copy the Breeze icons the app asks for into tarot_canvas/resources/icons.

The Mac has no icon theme, so the app carries a light and a dark subset of Breeze
there. Which names it needs is read off the source: every string literal in
tarot_canvas/ that Breeze has an icon for. That catches the names that reach
QIcon.fromTheme through tuples and parameters, which a grep for fromTheme("...")
would miss; a literal that only happens to share a name costs one small SVG.

    scripts/bundle_breeze_icons.py <breeze-icons checkout>

Run it through `just icons`, which pins the checkout.
"""

import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tarot_canvas"
OUTPUT = ROOT / "tarot_canvas" / "resources" / "icons"

CONTEXTS = {"actions": "Actions", "status": "Status", "places": "Places"}
SIZES = (16, 22)

# Breeze generates its dark theme at build time, by rewriting each icon's
# current-color-scheme stylesheet (tools/generate-symbolic-dark.cpp); these
# are the two colours it changes. Accent colours are left alone.
DARK_COLOURS = {"Text": "#fcfcfc", "Background": "#2a2e32"}

THEMES = {
    "breeze": ("Breeze", lambda svg: svg),
    "breeze-dark": ("Breeze Dark", lambda svg: darken(svg)),
}


def string_literals(source):
    for path in sorted(source.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield node.value


def breeze_icons(breeze):
    """{(context, size): {name: path}} for the directories bundled"""
    icons = {}
    for context in CONTEXTS:
        for size in SIZES:
            directory = breeze / "icons" / context / str(size)
            icons[context, size] = {p.stem: p for p in directory.glob("*.svg")}
    return icons


def darken(svg):
    def recolour(style):
        return re.sub(
            r"(\.ColorScheme-(\w+)\s*\{\s*color\s*:\s*)(#[0-9a-fA-F]+)",
            lambda m: m.group(1) + DARK_COLOURS.get(m.group(2), m.group(3)),
            style.group(0),
        )

    return re.sub(
        r'<style[^>]*id="current-color-scheme"[^>]*>.*?</style>', recolour, svg, flags=re.DOTALL
    )


def index_theme(name, directories, commit):
    lines = [
        f"# A subset of breeze-icons {commit}, written by scripts/bundle_breeze_icons.py",
        "[Icon Theme]",
        f"Name={name}",
        "Comment=Breeze by the KDE VDG",
        f"Directories={','.join(f'{c}/{s}' for c, s in directories)}",
    ]
    for context, size in directories:
        lines += ["", f"[{context}/{size}]", f"Size={size}"]
        lines += [f"Context={CONTEXTS[context]}", "Type=Fixed"]
    return "\n".join(lines) + "\n"


def main(breeze):
    breeze = Path(breeze).resolve()
    commit = subprocess.run(
        ["git", "-C", breeze, "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    icons = breeze_icons(breeze)
    known = set().union(*icons.values())
    names = sorted(known.intersection(string_literals(SOURCE)))
    directories = [key for key, found in icons.items() if found.keys() & set(names)]

    for theme, (title, transform) in THEMES.items():
        out = OUTPUT / theme
        shutil.rmtree(out, ignore_errors=True)
        for context, size in directories:
            (out / context / str(size)).mkdir(parents=True)
            for name in names:
                if path := icons[context, size].get(name):
                    # read_text follows Breeze's symlinks, which point across sizes
                    target = out / context / str(size) / f"{name}.svg"
                    target.write_text(transform(path.read_text()))
        (out / "index.theme").write_text(index_theme(title, directories, commit))
        shutil.copyfile(breeze / "COPYING-ICONS", out / "COPYING-ICONS")

    print(f"{len(names)} icons from breeze-icons {commit}:")
    print(" ".join(names))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
