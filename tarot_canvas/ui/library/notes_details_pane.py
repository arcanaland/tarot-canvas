from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.deck_details_pane import CoverWidget
from tarot_canvas.ui.notes_text import text as notes_text
from tarot_canvas.ui.tabs.card_view.notes_section import NoteRowsView


class NotesDetailsPane(QWidget):
    open_card_requested = pyqtSignal(str)  # the canonical card id
    open_note_requested = pyqtSignal(str, str)  # the canonical card id, the note's path

    HEADING_SCALE = 1.4
    CAPTION_SCALE = 0.85

    def __init__(self, parent=None):
        super().__init__(parent)
        self._details = None

        self.cover = CoverWidget(QSize(*units.cover_size(units.DENSITY_SMALL)))
        self.heading_label = _pane_text()
        self.heading_label.setFont(
            units.scaled_font(self.heading_label.font(), self.HEADING_SCALE, bold=True)
        )
        self.card_id_label = _pane_text()
        self.card_id_label.setFont(
            units.fixed_font(units.scaled_font(self.card_id_label.font(), self.CAPTION_SCALE))
        )
        self.card_id_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        heading_column = QVBoxLayout()
        heading_column.setContentsMargins(0, 0, 0, 0)
        heading_column.setSpacing(units.SMALL_SPACING)
        heading_column.addWidget(self.heading_label)
        heading_column.addWidget(self.card_id_label)
        heading_column.addStretch(1)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(units.LARGE_SPACING)
        header.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)
        header.addLayout(heading_column, 1)

        self.empty_label = _pane_text()
        self.empty_label.setEnabled(False)

        self.note_rows = NoteRowsView()
        self.note_rows.noteActivated.connect(self._on_note_activated)

        margin = units.GRID_UNIT
        body = QVBoxLayout()
        body.setContentsMargins(margin, 2 * units.LARGE_SPACING, margin, 0)
        body.setSpacing(units.LARGE_SPACING)
        body.addLayout(header)
        body.addSpacing(units.LARGE_SPACING)
        body.addWidget(self.note_rows)
        body.addWidget(self.empty_label)
        body.addStretch(1)

        content = QWidget()
        content.setLayout(body)

        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)

        self.open_button = QPushButton(QIcon.fromTheme("document-open"), notes_text("open_card"))
        self.open_button.clicked.connect(self._on_open)
        self.open_button.setVisible(bool(notes_text("open_card")))

        actions = QHBoxLayout()
        actions.setContentsMargins(margin, margin, margin, margin)
        actions.addWidget(self.open_button)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.scroll_area, 1)
        layout.addLayout(actions)

    def details(self):
        return self._details

    def show_details(self, details):
        previous, self._details = self._details, details
        if details is None:
            return

        self.heading_label.setText(details.name or "")
        self.heading_label.setVisible(bool(details.name))

        self.card_id_label.setText(details.card_id)

        self.cover.set_path(details.cover_path)

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


def _pane_text(text=""):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label
