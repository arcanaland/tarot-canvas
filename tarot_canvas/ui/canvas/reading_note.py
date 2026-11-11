"""A reading's one note: the oldest Markdown file in its folder, written a moment after each edit"""

import time
from pathlib import Path

from PyQt6.QtCore import QTimer, pyqtSlot
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.models.notes import read_directory
from tarot_canvas.models.reading_events import reading_events
from tarot_canvas.ui import typography, units
from tarot_canvas.ui.strings import CARD_VIEW, READINGS
from tarot_canvas.ui.tabs.card_view.markdown_editor import MarkdownEditor
from tarot_canvas.ui.tabs.card_view.note_editing import NoteLinks, write_note
from tarot_canvas.utils.logger import logger


def _written_at(path):
    """A note's timestamp prefix; a file without one sorts after every file with one"""
    prefix = path.stem.split("_", 1)[0]
    return (0, int(prefix), path.name) if prefix.isdigit() else (1, 0, path.name)


def note_path(folder):
    """The reading's note: the oldest of its notes, or None while it has none"""
    paths = sorted((note.path for note in read_directory(folder)), key=_written_at)
    if len(paths) > 1:
        others = ", ".join(path.name for path in paths[1:])
        logger.info(f"Reading {folder} shows note {paths[0].name}; it also holds {others}")
    return paths[0] if paths else None


class ReadingNote(QWidget):
    """The Notes header over the editor of a reading's note"""

    def __init__(self, tab, folder, interval):
        super().__init__()
        self.folder = Path(folder)
        self.path = note_path(self.folder)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        seam = QFrame()
        seam.setFrameShape(QFrame.Shape.HLine)
        seam.setFrameShadow(QFrame.Shadow.Plain)
        layout.addWidget(seam)

        header = QLabel(CARD_VIEW["tab_notes"])
        typography.apply(header, typography.Role.HEADING_4)
        margin = units.LARGE_SPACING
        # The header's row, which a pane may end with a button of its own
        self.header_row = QHBoxLayout()
        self.header_row.setContentsMargins(margin, margin, margin, units.SMALL_SPACING)
        self.header_row.setSpacing(units.SMALL_SPACING)
        self.header_row.addWidget(header, 1)
        layout.addLayout(self.header_row)

        # The editor asks its parent for link suggestions
        self.editor = MarkdownEditor(self)
        self.editor.setFrameShape(QFrame.Shape.NoFrame)
        self.editor.setPlaceholderText(READINGS["notes_hint"])
        self.editor.setAccessibleName(CARD_VIEW["tab_notes"])
        self.editor.set_deck_manager(deck_manager)
        header.setBuddy(self.editor)
        layout.addWidget(self.editor, 1)

        self.links = NoteLinks(tab, deck_manager, lambda: None)
        self.editor.linkClicked.connect(self.follow)

        if self.path is not None:
            try:
                self.editor.setPlainText(self.path.read_text(encoding="utf-8"))
            except OSError as error:
                logger.error(f"Could not read reading note {self.path}: {error}")
        self.editor.document().setModified(False)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(interval)
        self.timer.timeout.connect(self.write)
        self.editor.document().contentsChanged.connect(self.timer.start)

    def get_link_suggestions(self):
        """What the editor's link completer offers"""
        self.links.refresh()
        return self.links.suggestions()

    @pyqtSlot(str)
    def follow(self, link_text):
        self.links.refresh()
        self.links.follow(link_text)

    @pyqtSlot()
    def flush(self):
        """Write now if a write is waiting"""
        if self.timer.isActive():
            self.write()

    @pyqtSlot()
    def write(self):
        """Write the note; it gets a file at its first character that isn't blank"""
        self.timer.stop()
        if not self.editor.document().isModified():
            return
        content = self.editor.toPlainText()
        if self.path is None:
            if not content.strip():
                return
            self.path = self.folder / f"{int(time.time())}.md"
        try:
            write_note(str(self.path), content)
        except OSError as error:
            logger.error(f"Could not save reading note {self.path}: {error}")
            return
        self.editor.document().setModified(False)
        reading_events().readings_changed.emit()
