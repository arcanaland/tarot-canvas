"""Every note in the library, read from disk.

Notes are keyed by canonical card id, not by deck, so the whole corpus is one tree of
per-card directories. This module is the only reader of that tree: it is pure, takes its
base directory as an argument, and holds no state between calls.
"""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from tarot_canvas.models.coverage import CANONICAL_CARD_IDS, CellState
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import get_data_directory

NOTES_SUBPATH = "tarot-canvas/notes"


ATX_HEADING = re.compile(r"#{1,6}(\s|$)")


class Note(NamedTuple):
    card_id: str
    path: Path
    title: str
    modified: float
    has_body: bool
    first_line: str
    # Whether `first_line` came from an ATX heading the user wrote. A note with no
    # filename name is labelled by its first line either way, but `# Lyrics` is that
    # line being declared a title, where a bare sentence is just the note starting.
    first_line_is_heading: bool


def notes_base():
    """The running build's notes tree; state is partitioned by app ID, never unioned."""
    return get_data_directory(NOTES_SUBPATH)


def display_name_from_filename(filename):
    """A note's title, as written in the filename: <timestamp>_<name>.md

    A bare <timestamp>.md has no name in it, and gets "" rather than its own id: a note
    created from the Overview is unnamed until it is renamed, and views fall back to its
    first line.
    """
    name = filename.rsplit(".", 1)[0]

    if name.isdigit():
        return ""

    if "_" in name:
        stamp, rest = name.split("_", 1)
        if stamp.isdigit():
            name = rest

    return name.replace("_", " ")


def _lines(path):
    """Every non-blank line, stripped, in order."""
    try:
        with open(path, encoding="utf-8") as handle:
            return [line.strip() for line in handle.read().splitlines() if line.strip()]
    except OSError as error:
        logger.debug(f"Could not read note {path}: {error}")
        return []


def _strip_heading(line):
    return line.lstrip("#").strip() if ATX_HEADING.match(line) else line


def first_line_of(content):
    """A note's opening line as a view would label it: heading markers stripped.

    Takes text rather than a path so the card view can label a note it is still typing,
    without reading back the file it hasn't finished saving.
    """
    for line in content.splitlines():
        if line.strip():
            return _strip_heading(line.strip())
    return ""


def _body_of(lines):
    """Everything past an opening heading, or everything when there isn't one.

    Only an ATX heading is skipped. A note that opens with a blockquote, or with prose
    that happens to contain a `#`, has no heading and no line of it is the title.
    """
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
    """Every non-blank line past an opening heading, in order."""
    return _body_of(_lines(path))


def first_body_line(note):
    """The note's opening line of prose, past whatever a view already shows as its label.

    A named note is labelled by its filename, so its body begins after an opening
    heading. A nameless one is labelled by its own first line — that line is already on
    screen, and repeating it as the preview is how the same sentence came to appear
    twice in a row. Returns "" when the label was the whole note.
    """
    lines = _body_lines(note.path)

    if not note.title and lines and lines[0] == note.first_line:
        lines = lines[1:]

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
