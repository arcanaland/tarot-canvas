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

from tarot_canvas.models.ground import drawn
from tarot_canvas.ui import typography, units
from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.canvas.reading_note import note_path
from tarot_canvas.ui.canvas.saved_canvas import local_qdatetime
from tarot_canvas.ui.canvas.tab_icon import DIAGRAM, layout_marks, reading_marks
from tarot_canvas.ui.library.diagram import LayoutDiagram
from tarot_canvas.ui.library.readings.model import card_row_text, label
from tarot_canvas.ui.strings import READINGS
from tarot_canvas.ui.widgets.markdown_view import MarkdownView
from tarot_canvas.ui.widgets.pane_text import pane_text
from tarot_canvas.utils.dates import format_qdatetime
from tarot_canvas.utils.logger import logger


def _section_title(text):
    return typography.apply(pane_text(text), typography.Role.HEADING_4)


def _note_text(folder):
    """The reading's note as its tab edits it, or "" for none"""
    path = note_path(folder)
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        logger.warning(f"Could not read the reading's note {path}: {error}")
        return ""


class ReadingDetailsPane(QWidget):
    """A reading's Question and Date, its layout on its ground, its cards and its note"""

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
        self.note_view = MarkdownView()

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(units.LARGE_SPACING)
        body.addWidget(self.cards_title)
        body.addLayout(self.cards_column)
        body.addWidget(self.note_title)
        body.addWidget(self.note_view)
        body.addStretch(1)
        content = QWidget()
        content.setLayout(body)

        # Only the body scrolls; the heading and the diagram stay put
        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)

        self.diagram = LayoutDiagram()

        columns = QHBoxLayout()
        columns.setSpacing(units.GRID_UNIT)
        columns.addWidget(self.diagram)
        columns.addWidget(self.scroll_area, 1)

        margin = units.GRID_UNIT
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, 2 * units.LARGE_SPACING, margin, units.LARGE_SPACING)
        layout.setSpacing(units.LARGE_SPACING)
        layout.addLayout(heading_row)
        layout.addLayout(columns, 1)

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
            self.diagram.hide()
            return

        reading = row.reading
        self.heading_label.setText(label(reading))
        # Without a Question the heading is the Date already
        self.date_label.setText(format_qdatetime(local_qdatetime(reading.date)))
        self.date_label.setVisible(bool(reading.question))

        marks = reading_marks(reading, card_unit_size(), numbered=True)
        self.diagram.show_marks(layout_marks(marks, DIAGRAM.max_fill), drawn(reading.ground))

        while self.cards_column.count():
            self.cards_column.takeAt(0).widget().deleteLater()
        for card_row in row.card_rows:
            self.cards_column.addWidget(pane_text(card_row_text(card_row)))
        self.cards_title.setVisible(bool(row.card_rows))

        note = _note_text(row.path)
        self.note_view.set_markdown(note, base=row.path)
        self.note_title.setVisible(bool(note.strip()))
        self.note_view.setVisible(bool(note.strip()))

        if previous is None or previous.path != row.path:
            self.scroll_area.verticalScrollBar().setValue(0)

    def _on_open(self):
        if self._details is not None:
            self.open_requested.emit(self._details.path)
