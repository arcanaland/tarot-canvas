"""Every note in the library, read from disk.

Notes are keyed by canonical card id, not by deck, so the whole corpus is one tree of
per-card directories. This module is the only reader of that tree: it is pure, takes its
base directory as an argument, and holds no state between calls.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from tarot_canvas.models.coverage import CANONICAL_CARD_IDS, CellState
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import get_data_directory

NOTES_SUBPATH = "tarot-canvas/notes"


class Note(NamedTuple):
    card_id: str
    path: Path
    title: str
    modified: float
    has_body: bool


def notes_base():
    """The running build's notes tree; state is partitioned by app ID, never unioned."""
    return get_data_directory(NOTES_SUBPATH)


def display_name_from_filename(filename):
    """A note's title, as written in the filename: <timestamp>_<name>.md"""
    name = filename.rsplit(".", 1)[0]

    if "_" in name:
        stamp, rest = name.split("_", 1)
        if stamp.isdigit():
            name = rest

    return name.replace("_", " ")


def _has_body(path):
    """A note the user opened and left is a heading and nothing else."""
    try:
        with open(path, encoding="utf-8") as handle:
            lines = [line for line in handle.read().splitlines() if line.strip()]
    except OSError as error:
        logger.debug(f"Could not read note {path}: {error}")
        return False

    return len(lines) > 1


def _read_card_notes(card_dir):
    notes = []

    try:
        entries = sorted(card_dir.glob("*.md"))
    except OSError as error:
        logger.debug(f"Could not list notes in {card_dir}: {error}")
        return notes

    for path in entries:
        try:
            modified = path.stat().st_mtime
        except OSError as error:
            logger.debug(f"Could not stat note {path}: {error}")
            continue

        notes.append(
            Note(
                card_id=card_dir.name,
                path=path,
                title=display_name_from_filename(path.name),
                modified=modified,
                has_body=_has_body(path),
            )
        )

    notes.sort(key=lambda note: note.modified, reverse=True)
    return notes


def scan(base=None):
    """card_id -> its notes, newest first. Card directories with no notes are absent.

    A directory whose name isn't a canonical card id is kept: a note outlives the app's
    knowledge of the card it hangs on.
    """
    base = Path(base) if base is not None else notes_base()

    index = {}
    try:
        card_dirs = sorted(entry for entry in base.iterdir() if entry.is_dir())
    except OSError:
        return index

    for card_dir in card_dirs:
        notes = _read_card_notes(card_dir)
        if notes:
            index[card_dir.name] = notes

    return index


def coverage(index: Mapping[str, list[Note]]) -> list[CellState]:
    """One cell per canonical slot, in canonical order."""
    return [
        CellState.FILLED if index.get(card_id) else CellState.EMPTY
        for card_id in CANONICAL_CARD_IDS
    ]


def _body_lines(path):
    """Every non-blank line past the heading, in order."""
    try:
        with open(path, encoding="utf-8") as handle:
            lines = [line.strip() for line in handle.read().splitlines() if line.strip()]
    except OSError as error:
        logger.debug(f"Could not read note {path}: {error}")
        return []

    return lines[1:]


def first_body_line(note):
    """The note's opening line of prose, or "" for a note that is only its heading."""
    lines = _body_lines(note.path)
    return lines[0] if lines else ""


def matching_line(note, needle):
    """The first body line containing `needle`, or None. Read on demand, never cached.

    Nine notes is not a corpus, and a real full-text index would go stale the moment
    the card view writes.
    """
    if not needle:
        return None

    folded = needle.casefold()
    for line in _body_lines(note.path):
        if folded in line.casefold():
            return line

    return None
