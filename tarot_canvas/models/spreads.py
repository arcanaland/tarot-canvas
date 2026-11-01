import os
import re
import tempfile
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import get_data_directory

SPREADS_SUBPATH = "tarot-canvas/spreads"
SPREAD_FILE = "spread.toml"

_POSITION_ID = re.compile(r"p(\d+)")
_SPREAD_KEYS = {"name", "description", "sources", "positions"}
_POSITION_KEYS = {"id", "label", "meaning", "x", "y", "rotation", "z"}


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


def new_spread_dir(base=None):
    """A new folder named by the current time, or the next free second"""
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
    """p<n>, one past the largest n among the ids given"""
    numbers = [int(match[1]) for id in positions if (match := _POSITION_ID.fullmatch(id))]
    return f"p{max(numbers, default=0) + 1}"


def _position(table):
    try:
        return Position(
            id=str(table["id"]),
            label=str(table.get("label", "")),
            meaning=str(table.get("meaning", "")),
            x=float(table.get("x", 0.0)),
            y=float(table.get("y", 0.0)),
            rotation=float(table.get("rotation", 0.0)),
            z=float(table.get("z", 0.0)),
            extra={key: value for key, value in table.items() if key not in _POSITION_KEYS},
        )
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"bad position: {error!r}") from error


def load(path):
    """The Spread in folder path. Raises OSError or ValueError if it can't be read"""
    with open(Path(path) / SPREAD_FILE, "rb") as handle:
        table = tomllib.load(handle)

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
        extra={key: value for key, value in table.items() if key not in _SPREAD_KEYS},
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
    return {**table, **spread.extra}


def save(path, spread):
    """Write spread to folder path, whole or not at all"""
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


def scan(base=None):
    """(folder, Spread) for each readable spread, oldest first"""
    base = Path(base) if base is not None else spreads_base()
    try:
        folders = sorted(entry for entry in base.iterdir() if entry.is_dir())
    except OSError:
        return []

    spreads = []
    for folder in folders:
        try:
            spreads.append((folder, load(folder)))
        except (OSError, ValueError) as error:
            logger.warning(f"Skipping unreadable spread {folder}: {error}")
    return spreads
