"""Kept readings: readings/<timestamp>/reading.toml beside the reading's notes"""

from dataclasses import dataclass, replace
from datetime import date as Date
from datetime import datetime
from pathlib import Path

from tarot_canvas.models.ground import Ground
from tarot_canvas.models.spreads import Spread, spread_from_table, spread_table
from tarot_canvas.models.staged_delete import is_staged
from tarot_canvas.models.toml_files import (
    app_table,
    load_table,
    new_timestamped_dir,
    number,
    version_of,
    with_app_table,
    write_toml,
)
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import get_data_directory

READINGS_SUBPATH = "tarot-canvas/readings"
READING_FILE = "reading.toml"

VERSION = 1


@dataclass(frozen=True)
class ReadingCard:
    id: str
    reversed: bool = False
    # Resolved against the reading's default deck on load
    deck: str = ""
    # A position id of the reading's spread, or "" for none
    position: str = ""
    # False while the card still lies face-down
    turned: bool = True
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    rotation: float = 0.0


@dataclass(frozen=True)
class Reading:
    # When the reading was done
    date: datetime
    question: str = ""
    # The default deck for cards that name none
    deck: str = ""
    # Whether the deal could draw reversed cards, or None when nothing was dealt
    reversals: bool | None = None
    # A snapshot of the spread the reading was made with, and the folder it came from
    spread: Spread | None = None
    spread_from: str = ""
    cards: tuple = ()
    # The canvas's own ground, or None while it follows the default
    ground: Ground | None = None


def readings_base():
    return get_data_directory(READINGS_SUBPATH)


def new_reading_dir(base=None):
    """A new folder with the name as the current time"""
    return new_timestamped_dir(base if base is not None else readings_base())


# -- loading -------------------------------------------------------------------------------


def _typed(table, key, kind, default):
    value = table.get(key, default)
    # bool is an int, and an int is not a bool
    if not isinstance(value, kind) or (kind is not bool and isinstance(value, bool)):
        raise ValueError(f"{key} is not {kind.__name__}: {value!r}")
    return value


def _date(table):
    value = table.get("date")
    if isinstance(value, datetime):
        # A naive time is the reader's local time
        return value if value.tzinfo is not None else value.astimezone()
    if isinstance(value, Date):
        return datetime(value.year, value.month, value.day).astimezone()
    raise ValueError(f"no date: {value!r}")


def _card(entry, default_deck, geometry):
    if not isinstance(entry, dict):
        raise ValueError("not a table")
    return ReadingCard(
        id=_typed(entry, "id", str, None),
        reversed=_typed(entry, "reversed", bool, False),
        deck=_typed(entry, "deck", str, default_deck) or default_deck,
        position=_typed(entry, "position", str, ""),
        turned=_typed(entry, "turned", bool, True),
        **geometry,
    )


def _geometry(entry, index):
    """x, y, z and rotation from a layout entry, else the defaults for the card at index"""
    defaults = {"x": 0.0, "y": 0.0, "z": float(index), "rotation": 0.0}
    if entry is None:
        return defaults
    try:
        if not isinstance(entry, dict):
            raise ValueError("not a table")
        return {key: number(entry, key, default) for key, default in defaults.items()}
    except (ValueError, TypeError, OverflowError) as error:
        logger.warning(f"Reading layout {index} is unreadable, so it takes the default: {error}")
        return defaults


def _spread(table, path):
    """(snapshot, from) from the [spread] table; a bad one is dropped and the reading still loads"""
    snapshot = table.get("spread")
    if snapshot is None:
        return None, ""
    try:
        if not isinstance(snapshot, dict):
            raise ValueError("not a table")
        snapshot = dict(snapshot)
        origin = snapshot.pop("from", "")
        if not isinstance(origin, str):
            raise ValueError(f"from is not a string: {origin!r}")
        return spread_from_table(snapshot), origin
    except (ValueError, TypeError) as error:
        logger.warning(f"Dropped the unreadable spread of reading {path}: {error}")
        return None, ""


def _reading(table, path):
    try:
        ours = app_table(table)
    except ValueError as error:
        logger.warning(f"Ignored reading {path}'s app table: {error}")
        ours = {}
    try:
        version = version_of(ours)
    except ValueError as error:
        logger.warning(f"Ignored reading {path}'s version: {error}")
        version = VERSION
    if version > VERSION:
        logger.warning(
            f"Reading {path} was written by a newer Tarot Canvas (version {version}); "
            "loading what this one understands"
        )

    deck = _typed(table, "deck", str, "")
    reversals = table.get("reversals")
    if not isinstance(reversals, bool):
        if reversals is not None:
            logger.warning(f"Ignored reading {path}'s reversals: {reversals!r}")
        reversals = None

    entries = table.get("cards", [])
    if not isinstance(entries, list):
        raise ValueError("cards is not an array")
    layout = ours.get("layout", [])
    if not isinstance(layout, list):
        layout = []
    if len(layout) < len(entries):
        logger.info(f"Reading {path} has no layout for some cards, so they take the default")

    cards = []
    for index, entry in enumerate(entries):
        geometry = _geometry(layout[index] if index < len(layout) else None, index)
        try:
            cards.append(_card(entry, deck, geometry))
        except ValueError as error:
            logger.warning(f"Skipped card {index} of reading {path}: {error}")

    question = table.get("question", "")
    spread, origin = _spread(table, path)
    ground = None
    if "ground" in ours:
        ground = Ground.from_table(ours["ground"], Ground.from_settings())
    return Reading(
        date=_date(table),
        question=question if isinstance(question, str) else "",
        deck=deck,
        reversals=reversals,
        spread=spread,
        spread_from=origin,
        cards=tuple(cards),
        ground=ground,
    )


def load(path):
    """The Reading in folder path"""
    try:
        return _reading(load_table(Path(path) / READING_FILE), path)
    except (OSError, ValueError, TypeError) as error:
        logger.warning(f"Could not read reading {path}: {error}")
        return None


# -- saving --------------------------------------------------------------------------------


def _one_line(text):
    return " ".join(text.splitlines()).strip()


def _card_table(card, default_deck):
    table = {"id": card.id, "reversed": card.reversed}
    if card.deck and card.deck != default_deck:
        table["deck"] = card.deck
    if card.position:
        table["position"] = card.position
    if not card.turned:
        table["turned"] = False
    return table


def _table(reading):
    when = reading.date if reading.date.tzinfo is not None else reading.date.astimezone()
    table = {"date": when}
    question = _one_line(reading.question)
    if question:
        table["question"] = question
    if reading.deck:
        table["deck"] = reading.deck
    if reading.reversals is not None:
        table["reversals"] = reading.reversals
    if reading.spread is not None:
        snapshot = {"from": reading.spread_from} if reading.spread_from else {}
        # The spread's own app table belongs to the spread file, not to the copy
        snapshot.update((k, v) for k, v in spread_table(reading.spread).items() if k != "app")
        table["spread"] = snapshot
    table["cards"] = [_card_table(card, reading.deck) for card in reading.cards]
    layout = [
        {"x": card.x, "y": card.y, "z": card.z, "rotation": card.rotation} for card in reading.cards
    ]
    ours = {"version": VERSION, "layout": layout}
    # Only a ground of its own: a snapshot of the default would stop it following
    if reading.ground is not None:
        ours["ground"] = reading.ground.to_table()
    return with_app_table(table, ours)


def save(path, reading):
    """Write reading to folder path, replacing reading.toml whole; raises OSError"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    write_toml(path / READING_FILE, _table(reading))


def rename(path, question):
    """Give the reading in folder path a new Question; raises OSError, ValueError if unreadable"""
    reading = load(path)
    if reading is None:
        raise ValueError(f"no reading at {path}")
    save(path, replace(reading, question=question))


# -- scanning ------------------------------------------------------------------------------


def scan(base=None):
    """Scan all tarot readings in a base folder"""
    base = Path(base) if base is not None else readings_base()
    try:
        folders = [
            entry
            for entry in base.iterdir()
            if entry.is_dir() and not is_staged(entry) and (entry / READING_FILE).is_file()
        ]
    except OSError:
        return []

    readings = []
    for folder in folders:
        reading = load(folder)
        if reading is not None:
            readings.append((folder, reading))
    readings.sort(key=lambda pair: (pair[1].date, pair[0].name), reverse=True)
    return readings
