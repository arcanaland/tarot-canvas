"""No placeholder string is left anywhere in what ships."""

import subprocess
from pathlib import Path

import tarot_canvas

TAG = "clankertext"

ROOT = Path(tarot_canvas.__file__).parent.parent


def tagged_lines():
    """Tracked files only: build output under packaging/ is not ours."""
    tracked = (
        subprocess.run(
            ["git", "ls-files", "-z", "tarot_canvas", "packaging"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    return [
        f"{name}:{number}: {line.strip()}"
        for name in sorted(filter(None, tracked))
        if TAG.encode() in (ROOT / name).read_bytes()
        for number, line in enumerate(
            (ROOT / name).read_text(errors="replace").splitlines(), start=1
        )
        if TAG in line
    ]


def test_no_shipped_file_holds_a_placeholder():
    assert tagged_lines() == []
