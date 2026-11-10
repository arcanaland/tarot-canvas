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
from tarot_canvas.ui.canvas.saved_canvas import local_qdatetime
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.pane_text import pane_text
from tarot_canvas.ui.library.readings_model import label, newest_note_line
from tarot_canvas.ui.strings import READINGS
from tarot_canvas.utils.dates import format_qdatetime


def _section_title(text):
    return typography.apply(pane_text(text), typography.Role.HEADING_4)


class ReadingDetailsPane(QWidget):
    """A reading's Question and Date, its cards in order and its newest note's first line"""

    open_requested = pyqtSignal(object)  # the reading's folder

    def __init__(self, parent=None):
        super().__init__(parent)
        self._details = None

        self.heading_label = typography.apply(pane_text(), typography.Role.HEADING_1, primary=True)
        self.date_label = typography.apply(pane_text(), typography.Role.SMALL)
        self.date_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        self.open_button = QPushButton(QIcon.fromTheme("document-open"), READINGS["library_open"])
        self.open_button.clicked.connect(self._on_open)

        heading_column = QVBoxLayout()
        heading_column.setContentsMargins(0, 0, 0, 0)
        heading_column.setSpacing(units.SMALL_SPACING)
        heading_column.addWidget(self.heading_label)
        heading_column.addWidget(self.date_label)

        heading_row = QHBoxLayout()
        heading_row.setContentsMargins(0, 0, 0, 0)
        heading_row.setSpacing(units.LARGE_SPACING)
        heading_row.addLayout(heading_column, 1)
        heading_row.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignTop)

        self.cards_title = _section_title(READINGS["library_cards"])
        self.cards_column = QVBoxLayout()
        self.cards_column.setContentsMargins(0, 0, 0, 0)
        self.cards_column.setSpacing(units.SMALL_SPACING)
        self.note_title = _section_title(READINGS["library_note"])
        self.note_label = pane_text()

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(units.LARGE_SPACING)
        body.addWidget(self.cards_title)
        body.addLayout(self.cards_column)
        body.addWidget(self.note_title)
        body.addWidget(self.note_label)
        body.addStretch(1)
        content = QWidget()
        content.setLayout(body)

        # Only the body scrolls; the heading stays put
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
        """The ReadingRow shown, or None"""
        return self._details

    def card_lines(self):
        return [
            self.cards_column.itemAt(n).widget().text() for n in range(self.cards_column.count())
        ]

    def show_details(self, row):
        previous, self._details = self._details, row
        if row is None:
            return

        reading = row.reading
        self.heading_label.setText(label(reading))
        # Without a Question the heading is the Date already
        self.date_label.setText(format_qdatetime(local_qdatetime(reading.date)))
        self.date_label.setVisible(bool(reading.question))

        while self.cards_column.count():
            self.cards_column.takeAt(0).widget().deleteLater()
        for line in row.card_lines:
            self.cards_column.addWidget(pane_text(line))
        self.cards_title.setVisible(bool(row.card_lines))

        note = newest_note_line(row)
        self.note_label.setText(note)
        self.note_title.setVisible(bool(note))
        self.note_label.setVisible(bool(note))

        if previous is None or previous.path != row.path:
            self.scroll_area.verticalScrollBar().setValue(0)

    def _on_open(self):
        if self._details is not None:
            self.open_requested.emit(self._details.path)
