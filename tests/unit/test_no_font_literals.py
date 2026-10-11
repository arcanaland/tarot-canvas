"""Only the typography module sets a font's size or family.

Anywhere else, a literal ignores the user's system font, and an explicit size stops
a widget following a change to it.
"""

import re
import subprocess
from pathlib import Path

import tarot_canvas

ROOT = Path(tarot_canvas.__file__).parent.parent

LITERAL = re.compile(r'font-size|QFont\("|setPixelSize|setPointSize')


def files_with_font_literals():
    tracked = (
        subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "tarot_canvas"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    return sorted(
        name
        for name in tracked
        if name.endswith(".py")
        and (ROOT / name).exists()
        and LITERAL.search((ROOT / name).read_text(encoding="utf-8"))
    )


def test_only_typography_sets_a_font_size_or_family():
    assert files_with_font_literals() == ["tarot_canvas/ui/typography.py"]
