"""The notes view's details pane: one card, and what is written on it.

Deliberately read-only. Every write to a note goes through the card view's Notes
tab, so there is one code path that mutates a file and one autosave timer over it.
"""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QIcon, QPainter, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models import notes as notes_model
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.deck_details_pane import CoverWidget
from tarot_canvas.ui.library.notes_model import modified_text
from tarot_canvas.ui.library.notes_text import text as notes_text


class NotesDetailsPane(QWidget):
    open_card_requested = pyqtSignal(str)  # the canonical card id

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
        self.card_id_label.setFont(units.scaled_font(self.card_id_label.font(), self.CAPTION_SCALE))
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

        self.notes_group_label = _pane_text()
        self.notes_group_label.setFont(units.scaled_font(self.notes_group_label.font(), bold=True))
        self.empty_label = _pane_text()
        self.empty_label.setEnabled(False)

        self.notes_column = QVBoxLayout()
        self.notes_column.setContentsMargins(0, 0, 0, 0)
        self.notes_column.setSpacing(units.LARGE_SPACING)

        margin = units.GRID_UNIT
        body = QVBoxLayout()
        body.setContentsMargins(margin, 2 * units.LARGE_SPACING, margin, 0)
        body.setSpacing(units.LARGE_SPACING)
        body.addLayout(header)
        body.addSpacing(units.LARGE_SPACING)
        body.addWidget(self.notes_group_label)
        body.addLayout(self.notes_column)
        body.addWidget(self.empty_label)
        body.addStretch(1)

        content = QWidget()
        content.setLayout(body)

        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)

        # Hidden until Adam has a word for it; the list opens a card by activation
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

        label = notes_text("card_id_label")
        self.card_id_label.setText(f"{label} {details.card_id}" if label else details.card_id)

        self.cover.set_path(details.cover_path)

        group = notes_text("notes_group_label")
        self.notes_group_label.setText(group)
        self.notes_group_label.setVisible(bool(group) and bool(details.notes))

        self._rebuild_notes(details.notes)

        empty = notes_text("no_notes_on_card")
        self.empty_label.setText(empty)
        self.empty_label.setVisible(bool(empty) and not details.notes)

        self.open_button.setText(notes_text("open_card"))
        self.open_button.setVisible(bool(notes_text("open_card")))

        if previous is None or previous.card_id != details.card_id:
            self.scroll_area.verticalScrollBar().setValue(0)

    def note_widgets(self):
        """The per-note blocks now shown, top to bottom."""
        return [self.notes_column.itemAt(row).widget() for row in range(self.notes_column.count())]

    def _rebuild_notes(self, notes):
        while self.notes_column.count():
            item = self.notes_column.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        for note in notes:
            self.notes_column.addWidget(_NoteBlock(note))

    def _on_open(self):
        if self._details is not None:
            self.open_card_requested.emit(self._details.card_id)


class _NoteBlock(QWidget):
    """One note: what it's called, when it was written, and how it opens."""

    CAPTION_SCALE = 0.85

    def __init__(self, note, parent=None):
        super().__init__(parent)
        self.note = note

        title = _pane_text(notes_model.label(note))
        title.setFont(units.scaled_font(title.font(), bold=True))

        date = _pane_text(modified_text(note.modified))
        date.setFont(units.scaled_font(date.font(), self.CAPTION_SCALE))
        date.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        # A stub the user made and left says so only once Adam has the words for it
        first_line = notes_model.first_body_line(note) or notes_text("stub_note")
        self.body_label = _ElidedLabel(first_line)
        self.body_label.setVisible(bool(first_line))

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(title)
        column.addWidget(date)
        column.addWidget(self.body_label)


class _ElidedLabel(QLabel):
    """One line of the note, cut at the pane's edge rather than widening it."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setPen(self.palette().text().color())
        metrics = QFontMetrics(self.font())
        painter.drawText(
            self.rect(),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width()),
        )
        painter.end()


def _pane_text(text=""):
    label = QLabel(text)
    # A note is the user's own writing, shown as written
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label
