"""Marker file that's used in case OpenGL freaks out."""

import configparser
import json
import logging
import os
from functools import cache
from pathlib import Path

from PyQt6.QtCore import qVersion

from tarot_canvas._version import __version__
from tarot_canvas.utils.files import write_atomic
from tarot_canvas.utils.path_helper import get_cache_directory

FLATPAK_INFO = Path("/.flatpak-info")
GL_EXTENSION = "org.freedesktop.Platform.GL"

log = logging.getLogger(__name__)


def marker_key(app_version, qt_version, kernel, flatpak_info):
    """What GL's behaviour depends on."""
    if flatpak_info is None:
        return [app_version, qt_version, kernel]

    info = configparser.ConfigParser(interpolation=None, strict=False)
    info.read_string(flatpak_info)
    instance = info["Instance"] if info.has_section("Instance") else {}
    extensions = instance.get("runtime-extensions", "").split(";")
    drivers = sorted(entry for entry in extensions if entry.startswith(GL_EXTENSION))
    return [app_version, instance.get("runtime-commit", ""), *drivers, kernel]


@cache
def current_key():
    try:
        flatpak_info = FLATPAK_INFO.read_text()
    except FileNotFoundError:
        flatpak_info = None
    return marker_key(__version__, qVersion(), os.uname().release, flatpak_info)


def marker_path():
    return get_cache_directory("tarot-canvas/gl-check.json")


def clear_marker():
    GlMarker(marker_path(), None).clear()


class GlMarker:
    def __init__(self, path, key):
        self.path = path
        self.key = key

    def failed(self):
        """True when an earlier launch died in a GL stage with this key. Otherwise arms the probe."""
        try:
            data = json.loads(self.path.read_bytes())
        except FileNotFoundError:
            data = None
        except (OSError, ValueError):
            data = {}
        if isinstance(data, dict) and data.get("key") == self.key:
            self.fail(data.get("stage"))
            return True
        if data is not None:
            self.clear()
            log.info("GL components changed since GL last failed; trying GL again")
        self.arm("probe")
        return False

    def arm(self, stage):
        self._write("trying", stage)

    def fail(self, stage):
        log.warning(
            "GL failed at stage %s",
            stage,
        )
        self._write("failed", stage)

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            log.exception("Could not delete the GL marker")

    def _write(self, state, stage):
        body = json.dumps({"key": self.key, "state": state, "stage": stage})
        try:
            write_atomic(self.path, body.encode())
        except OSError:
            log.exception("Could not write the GL marker")
