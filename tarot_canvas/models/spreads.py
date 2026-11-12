import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from tarot_canvas.models.staged_delete import is_staged
from tarot_canvas.models.toml_files import (
    load_table,
    new_timestamped_dir,
    number,
    take_app_fields,
    version_of,
    with_app_table,
    write_toml,
)
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import BUNDLED_SPREADS_PATH, get_data_directory

SPREADS_SUBPATH = "tarot-canvas/spreads"
SPREAD_FILE = "spread.toml"

_POSITION_ID = re.compile(r"p(\d+)")
_SPREAD_KEYS = {"name", "description", "sources", "positions"}
_POSITION_KEYS = {"id", "label", "meaning", "x", "y", "rotation", "z"}

VERSION = 1


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


def copy_of(spread, path):
    """spread as a copy of the one in folder path; a built-in's credits stay with the built-in"""
    return replace(spread, sources=()) if is_included(path) else spread


def new_spread_dir(base=None):
    """A new folder with the name as the current time"""
    return new_timestamped_dir(base if base is not None else spreads_base())


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


def position_from_table(table):
    """A Position from its TOML table, else ValueError"""
    try:
        return Position(
            id=str(table["id"]),
            label=str(table.get("label", "")),
            meaning=str(table.get("meaning", "")),
            x=number(table, "x"),
            y=number(table, "y"),
            rotation=number(table, "rotation"),
            z=number(table, "z"),
            extra={key: value for key, value in table.items() if key not in _POSITION_KEYS},
        )
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError(f"bad position: {error!r}") from error


def _take_version(extra):
    """The file's version, removing it from extra's app table (absent is 1)"""
    return version_of(take_app_fields(extra, {"version"}))


def load(path):
    return spread_from_table(load_table(Path(path) / SPREAD_FILE))


def spread_from_table(table):
    """A Spread from its TOML table, else ValueError"""
    # if [meta] is there, the file might be from a future spec that we're not aware of yet
    if "meta" in table:
        raise ValueError("written for an unknown spread spec")

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
        positions=tuple(position_from_table(position) for position in positions),
        extra=extra,
    )


def position_table(position):
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


def spread_table(spread):
    """spread as its TOML table, without the app's own table"""
    table = {"name": spread.name}
    if spread.description:
        table["description"] = spread.description
    if spread.sources:
        table["sources"] = list(spread.sources)
    table["positions"] = [position_table(position) for position in spread.positions]
    table.update(spread.extra)
    return table


def save(path, spread):
    """Write spread to folder path"""
    table = with_app_table(spread_table(spread), {"version": VERSION})
    write_toml(Path(path) / SPREAD_FILE, table)


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
