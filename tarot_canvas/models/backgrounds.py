"""The images a canvas ground can be, as copies the app owns"""

import filecmp
import os
import shutil
from pathlib import Path

from PyQt6.QtGui import QImageReader

from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import get_data_directory

BACKGROUNDS_SUBPATH = "tarot-canvas/backgrounds"
PART_SUFFIX = ".part"


def backgrounds_base():
    return get_data_directory(BACKGROUNDS_SUBPATH)


def image_suffixes():
    return {"." + bytes(name).decode().lower() for name in QImageReader.supportedImageFormats()}


def background_path(name):
    """The copy called name, or None for a name that isn't a bare file name"""
    if not name or Path(name).name != name or name in (".", ".."):
        return None
    return backgrounds_base() / name


def list_backgrounds():
    """The file names of the copies, in name order"""
    base = backgrounds_base()
    try:
        entries = list(base.iterdir())
    except OSError:
        return []
    suffixes = image_suffixes()
    return sorted(
        (entry.name for entry in entries if entry.is_file() and entry.suffix.lower() in suffixes),
        key=str.casefold,
    )


def _free_name(base, stem, suffix):
    candidate = stem + suffix
    number = 2
    while (base / candidate).exists():
        candidate = f"{stem}-{number}{suffix}"
        number += 1
    return candidate


def add_background(source):
    """Copy an image file in; its new file name, or None if it isn't an image Qt can read.

    Adding the same file twice returns the first copy's name.
    """
    source = Path(source)
    if not QImageReader(str(source)).canRead():
        logger.warning(f"Not adding {source} as a background: not a readable image")
        return None
    suffix = source.suffix.lower()
    if suffix not in image_suffixes():
        suffix = "." + bytes(QImageReader(str(source)).format()).decode().lower()

    base = backgrounds_base()
    part = None
    try:
        base.mkdir(parents=True, exist_ok=True)
        existing = base / (source.stem + suffix)
        if existing.is_file() and filecmp.cmp(source, existing, shallow=False):
            return existing.name
        name = _free_name(base, source.stem, suffix)
        part = base / (name + PART_SUFFIX)
        shutil.copyfile(source, part)
        os.replace(part, base / name)
    except OSError as error:
        logger.error(f"Could not copy {source} into {base}: {error}")
        if part is not None:
            part.unlink(missing_ok=True)
        return None
    return name


def remove_background(name):
    path = background_path(name)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        logger.error(f"Could not remove the background {path}: {error}")
