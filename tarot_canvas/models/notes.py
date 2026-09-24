import re
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS
from tarot_canvas.models.coverage import CellState
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import get_data_directory

NOTES_SUBPATH = "tarot-canvas/notes"


# a markdown header
ATX_HEADING = re.compile(r"#{1,6}(\s|$)")


class Note(NamedTuple):
    card_id: str
    path: Path
    title: str
    modified: float
    has_body: bool
    first_line: str
    first_line_is_heading: bool


def notes_base():
    return get_data_directory(NOTES_SUBPATH)


def display_name_from_filename(filename):
    """A note's title from filename: <timestamp>_<name>.md"""
    name = filename.rsplit(".", 1)[0]

    if name.isdigit():
        return ""

    if "_" in name:
        stamp, rest = name.split("_", 1)
        if stamp.isdigit():
            name = rest

    return name.replace("_", " ")


def _lines(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return [line.strip() for line in handle.read().splitlines() if line.strip()]
    except OSError as error:
        logger.debug(f"Could not read note {path}: {error}")
        return []


def _strip_heading(line):
    return line.lstrip("#").strip() if ATX_HEADING.match(line) else line


def label(note):
    """name or opening line."""
    return note.title or note.first_line


def first_line_of(content):
    for line in content.splitlines():
        if line.strip():
            return _strip_heading(line.strip())
    return ""


def _body_of(lines):
    """Everything past an opening heading"""
    if lines and ATX_HEADING.match(lines[0]):
        return lines[1:]

    return lines


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

        lines = _lines(path)
        notes.append(
            Note(
                card_id=card_dir.name,
                path=path,
                title=display_name_from_filename(path.name),
                modified=modified,
                has_body=bool(_body_of(lines)),
                first_line=_strip_heading(lines[0]) if lines else "",
                first_line_is_heading=bool(lines) and bool(ATX_HEADING.match(lines[0])),
            )
        )

    notes.sort(key=lambda note: note.modified, reverse=True)
    return notes


def scan(base=None):
    """Dict of card_id to notes"""
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
    return _body_of(_lines(path))


def first_body_line(note):
    """The note's opening line of prose"""
    if not note.has_body:
        return ""

    lines = _body_lines(note.path)

    if not note.title and lines and lines[0] == note.first_line:
        lines = lines[1:]

    return lines[0] if lines else ""


def matching_line(note, needle):
    """first line containing needle or None"""
    if not needle:
        return None

    folded = needle.casefold()
    return next(
        (line for line in _body_lines(note.path) if folded in line.casefold()),
        None,
    )
