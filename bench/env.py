"""Process setup that has to happen before Qt or tarot_canvas are imported."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# Large enough that CanvasTab.ensure_window_bounds never shrinks the bench window
SCREEN_WIDTH = 2560
SCREEN_HEIGHT = 1600


class BenchError(Exception):
    """A run that would produce a meaningless number."""


def isolate_home():
    """Point $HOME and XDG at a scratch directory"""
    home = Path(tempfile.mkdtemp(prefix="tarot-canvas-bench-"))
    os.environ["HOME"] = str(home)
    os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
    os.environ["XDG_DATA_HOME"] = str(home / ".local" / "share")
    os.environ["XDG_CACHE_HOME"] = str(home / ".cache")
    return home


def select_platform(platform, dpr, scratch):
    """Set QT_QPA_PLATFORM, giving offscreen a screen of known size and dpr."""
    if platform == "offscreen":
        config = scratch / "offscreen.json"
        screen = {
            "name": "bench",
            "x": 0,
            "y": 0,
            "width": SCREEN_WIDTH,
            "height": SCREEN_HEIGHT,
            "logicalDpi": 96,
            "dpr": dpr,
        }
        config.write_text(json.dumps({"screens": [screen]}))
        os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={config}"
    else:
        if dpr != 1:
            raise BenchError("--dpr only applies offscreen; scale the compositor instead")
        os.environ["QT_QPA_PLATFORM"] = platform


def unthrottle(msaa):
    """Render as fast as possible (avoid vsync)"""
    from PyQt6.QtGui import QSurfaceFormat

    fmt = QSurfaceFormat.defaultFormat()
    fmt.setSwapInterval(0)
    fmt.setSamples(msaa)
    QSurfaceFormat.setDefaultFormat(fmt)


def machine():
    """What produced a result, so two result files can be judged comparable."""
    import platform as host

    from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

    info = {
        "python": host.python_version(),
        "qt": QT_VERSION_STR,
        "pyqt": PYQT_VERSION_STR,
        "kernel": host.release(),
        "cpu": _cpu_model(),
        "governor": _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
    }
    info.update(_git())
    return info


def _read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _cpu_model():
    for line in (_read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()
    return None


def _git():
    if shutil.which("git") is None:
        return {}
    root = Path(__file__).resolve().parent.parent

    def git(*args):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None

    return {
        "commit": git("rev-parse", "--short", "HEAD"),
        "dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
    }
