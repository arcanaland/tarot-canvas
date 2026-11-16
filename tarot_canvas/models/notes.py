import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS
from tarot_canvas.models.coverage import CellState
from tarot_canvas.utils.path_helper import get_data_directory

log = logging.getLogger(__name__)

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


class NoteAnchor(NamedTuple):
    """Where a set of notes lives: the directory they are listed from and written to,
    and the card they are about, if they are about one."""

    directory: Path
    card_id: str | None = None


def notes_base():
    return get_data_directory(NOTES_SUBPATH)


def card_anchor(card_id):
    return NoteAnchor(notes_base() / card_id, card_id)


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
    except (OSError, UnicodeDecodeError) as error:
        log.debug("Could not read note %s: %s", path, error)
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


def read_directory(directory):
    """The notes in one directory, newest first; a missing directory has none.

    Each note's `card_id` is the directory's name, which is the card's for a card's notes.
    """
    directory = Path(directory)
    notes = []

    try:
        entries = sorted(directory.glob("*.md"))
    except OSError as error:
        log.debug("Could not list notes in %s: %s", directory, error)
        return notes

    for path in entries:
        # A copy to a disk macOS can't tag leaves its metadata in a ._ file beside each note
        if path.name.startswith("._"):
            continue
        try:
            modified = path.stat().st_mtime
        except OSError as error:
            log.debug("Could not stat note %s: %s", path, error)
            continue

        lines = _lines(path)
        notes.append(
            Note(
                card_id=directory.name,
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
        notes = read_directory(card_dir)
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
