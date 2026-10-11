from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui import typography
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.pane_text import pane_text
from tarot_canvas.ui.notes_text import text as notes_text
from tarot_canvas.ui.tabs.card_view.notes_section import NoteRowsView


class NotesDetailsPane(QWidget):
    open_card_requested = pyqtSignal(str)  # the canonical card id
    open_note_requested = pyqtSignal(str, str)  # the canonical card id, the note's path

    def __init__(self, parent=None):
        super().__init__(parent)
        self._details = None

        self.heading_label = typography.apply(pane_text(), typography.Role.HEADING_1, primary=True)
        self.card_id_label = typography.apply(pane_text(), typography.Role.SMALL, fixed=True)
        self.card_id_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        self.open_button = QPushButton(QIcon.fromTheme("document-open"), notes_text("open_card"))
        self.open_button.clicked.connect(self._on_open)
        self.open_button.setVisible(bool(notes_text("open_card")))

        heading_column = QVBoxLayout()
        heading_column.setContentsMargins(0, 0, 0, 0)
        heading_column.setSpacing(units.SMALL_SPACING)
        heading_column.addWidget(self.heading_label)
        heading_column.addWidget(self.card_id_label)

        # The name and id, with the card's one action at the far end, as a mail's subject line
        heading_row = QHBoxLayout()
        heading_row.setContentsMargins(0, 0, 0, 0)
        heading_row.setSpacing(units.LARGE_SPACING)
        heading_row.addLayout(heading_column, 1)
        heading_row.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignTop)

        self.empty_label = pane_text()
        self.empty_label.setEnabled(False)

        self.note_rows = NoteRowsView()
        self.note_rows.noteActivated.connect(self._on_note_activated)

        thread = QVBoxLayout()
        thread.setContentsMargins(0, 0, 0, 0)
        thread.setSpacing(units.LARGE_SPACING)
        thread.addWidget(self.note_rows)
        thread.addWidget(self.empty_label)
        thread.addStretch(1)

        content = QWidget()
        content.setLayout(thread)

        # Only the thread scrolls; the heading stays put
        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)

        margin = units.GRID_UNIT
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, 2 * units.LARGE_SPACING, margin, units.LARGE_SPACING)
        layout.setSpacing(units.LARGE_SPACING)
        layout.addLayout(heading_row)
        layout.addWidget(self.scroll_area, 1)

    def details(self):
        return self._details

    def show_details(self, details):
        previous, self._details = self._details, details
        if details is None:
            return

        self.heading_label.setText(details.name or "")
        self.heading_label.setVisible(bool(details.name))

        self.card_id_label.setText(details.card_id)

        self.note_rows.set_notes(details.notes)
        self.note_rows.setVisible(bool(details.notes))

        empty = notes_text("no_notes_on_card")
        self.empty_label.setText(empty)
        self.empty_label.setVisible(bool(empty) and not details.notes)

        self.open_button.setText(notes_text("open_card"))
        self.open_button.setVisible(bool(notes_text("open_card")))

        if previous is None or previous.card_id != details.card_id:
            self.scroll_area.verticalScrollBar().setValue(0)

    def _on_note_activated(self, path):
        if self._details is not None:
            self.open_note_requested.emit(self._details.card_id, path)

    def _on_open(self):
        if self._details is not None:
            self.open_card_requested.emit(self._details.card_id)
