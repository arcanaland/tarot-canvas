import os
import re
import tempfile
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

from tarot_canvas.models.staged_delete import is_staged
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import BUNDLED_SPREADS_PATH, get_data_directory

SPREADS_SUBPATH = "tarot-canvas/spreads"
SPREAD_FILE = "spread.toml"

_POSITION_ID = re.compile(r"p(\d+)")
_SPREAD_KEYS = {"name", "description", "sources", "positions"}
_POSITION_KEYS = {"id", "label", "meaning", "x", "y", "rotation", "z"}

APP_TABLE = "land.arcana.tarotcanvas"
VERSION = 1

# Far past any layout, and well inside what the canvas and z's arithmetic can hold
MAX_NUMBER = 1e9
# Far past any spread, and shallow enough that a file that loads can be saved again
MAX_NESTING = 32


@dataclass(frozen=True)
class Position:
    id: str
    label: str = ""
    meaning: str = ""
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0
    z: float = 0.0
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Spread:
    name: str = ""
    description: str = ""
    sources: tuple = ()
    positions: tuple = ()
    extra: dict = field(default_factory=dict)


def spreads_base():
    return get_data_directory(SPREADS_SUBPATH)


def included_base():
    """The spreads that ship with the app, read-only and rewritten by each release"""
    return BUNDLED_SPREADS_PATH


def is_included(path):
    """Whether folder path is one of the spreads that ship with the app"""
    if path is None:
        return False
    try:
        return Path(path).resolve().is_relative_to(Path(included_base()).resolve())
    except OSError:
        return False


def new_spread_dir(base=None):
    """A new folder with the name as the current time"""
    base = Path(base) if base is not None else spreads_base()
    base.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    while True:
        path = base / str(stamp)
        try:
            path.mkdir()
        except FileExistsError:
            stamp += 1
        else:
            return path


def next_position_id(positions):
    numbers = [int(match[1]) for id in positions if (match := _POSITION_ID.fullmatch(id))]
    return f"p{max(numbers, default=0) + 1}"


def offsets_from_middle(centres, unit, places=3):
    """(x, y) of each centre, in units, from the middle of the centres' bounding box"""
    if not centres:
        return []
    xs, ys = zip(*centres, strict=True)
    middle_x, middle_y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return [
        (round((x - middle_x) / unit, places), round((y - middle_y) / unit, places))
        for x, y in centres
    ]


def _nesting(value):
    if isinstance(value, dict):
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return 0
    return 1 + max(map(_nesting, children), default=0)


def _number(table, key):
    value = float(table.get(key, 0.0))
    if not abs(value) <= MAX_NUMBER:  # nan compares false
        raise ValueError(f"{key} is out of range: {value}")
    return value


def _position(table):
    try:
        return Position(
            id=str(table["id"]),
            label=str(table.get("label", "")),
            meaning=str(table.get("meaning", "")),
            x=_number(table, "x"),
            y=_number(table, "y"),
            rotation=_number(table, "rotation"),
            z=_number(table, "z"),
            extra={key: value for key, value in table.items() if key not in _POSITION_KEYS},
        )
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError(f"bad position: {error!r}") from error


def _take_version(extra):
    """The file's version, removing it from extra's app table (absent is 1)"""
    apps = extra.get("app")
    if apps is None:
        return 1
    if not isinstance(apps, dict):
        raise ValueError("app is not a table")
    ours = apps.get(APP_TABLE)
    if ours is None:
        return 1
    if not isinstance(ours, dict):
        raise ValueError(f"app.{APP_TABLE} is not a table")

    # actually read version now
    version = ours.pop("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError(f"bad version: {version!r}")
    if not ours:
        del apps[APP_TABLE]
    if not apps:
        del extra["app"]
    return version


def load(path):
    with open(Path(path) / SPREAD_FILE, "rb") as handle:
        try:
            table = tomllib.load(handle)
            too_deep = _nesting(table) > MAX_NESTING
        except RecursionError:
            too_deep = True
    if too_deep:
        raise ValueError("nested too deeply")

    extra = {key: value for key, value in table.items() if key not in _SPREAD_KEYS}
    version = _take_version(extra)
    if version > VERSION:
        raise ValueError(f"written by a newer Tarot Canvas (version {version})")

    sources = table.get("sources", [])
    positions = table.get("positions", [])
    if not isinstance(positions, list) or not isinstance(sources, list):
        raise ValueError("positions and sources must be arrays")
    if not all(isinstance(source, dict) for source in sources):
        raise ValueError("a source is not a table")

    return Spread(
        name=str(table.get("name", "")),
        description=str(table.get("description", "")),
        sources=tuple(sources),
        positions=tuple(_position(position) for position in positions),
        extra=extra,
    )


def _position_table(position):
    return {
        "id": position.id,
        "label": position.label,
        "meaning": position.meaning,
        "x": position.x,
        "y": position.y,
        "rotation": position.rotation,
        "z": position.z,
        **position.extra,
    }


def _table(spread):
    table = {"name": spread.name}
    if spread.description:
        table["description"] = spread.description
    if spread.sources:
        table["sources"] = list(spread.sources)
    table["positions"] = [_position_table(position) for position in spread.positions]
    table.update(spread.extra)
    apps = dict(table.get("app", {}))
    apps[APP_TABLE] = {**apps.get(APP_TABLE, {}), "version": VERSION}
    table["app"] = apps
    return table


def save(path, spread):
    """Write spread to folder path"""
    path = Path(path)
    text = tomli_w.dumps(_table(spread), multiline_strings=True)
    descriptor, temporary = tempfile.mkstemp(dir=path, prefix=f".{SPREAD_FILE}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path / SPREAD_FILE)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def edited_at(path):
    """When the spread in folder path was last saved, or 0 if that can't be read"""
    try:
        return (Path(path) / SPREAD_FILE).stat().st_mtime
    except OSError:
        return 0.0


def scan(base=None):
    """(folder, Spread) for each readable spread (oldest first)"""
    base = Path(base) if base is not None else spreads_base()
    try:
        folders = sorted(
            entry for entry in base.iterdir() if entry.is_dir() and not is_staged(entry)
        )
    except OSError:
        return []

    spreads = []
    for folder in folders:
        try:
            spreads.append((folder, load(folder)))
        except (OSError, ValueError) as error:
            logger.warning(f"Skipping unreadable spread {folder}: {error}")
    return spreads


def scan_included():
    """(folder, Spread) for each spread that ships with the app"""
    return scan(included_base())
