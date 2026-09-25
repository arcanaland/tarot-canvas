"""No placeholder string is left anywhere in what ships."""

import subprocess
from pathlib import Path

import tarot_canvas

TAG = "clankertext"

ROOT = Path(tarot_canvas.__file__).parent.parent


def tagged_files():
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
    return sorted(name for name in tracked if name and TAG.encode() in (ROOT / name).read_bytes())


def test_no_shipped_file_holds_a_placeholder():
    assert tagged_files() == []
