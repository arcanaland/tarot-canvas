import math

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
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
from tarot_canvas.ui.canvas.tab_icon import DIAGRAM, layout_marks, reading_marks
from tarot_canvas.ui.library.diagram import LayoutDiagram
from tarot_canvas.ui.library.readings.model import (
    card_row_text,
    is_sandbox,
    label,
    meta_text,
    open_icon,
    open_text,
)
from tarot_canvas.ui.strings import READINGS
from tarot_canvas.ui.widgets.expand_button import ExpandButton
from tarot_canvas.ui.widgets.markdown_view import MarkdownView
from tarot_canvas.ui.widgets.pane_text import pane_text
from tarot_canvas.utils.logger import logger


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


class _CardColumns(QWidget):
    """Card rows down a column, flowing into the next past ROWS_PER_COLUMN"""

    ROWS_PER_COLUMN = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels = []
        self._columns = 0
        self._grid = None
        self._new_grid()

    def _new_grid(self):
        # A fresh grid each time: a QGridLayout keeps every row and column it ever had
        if self._grid is not None:
            QWidget().setLayout(self._grid)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(units.GRID_UNIT)
        self._grid.setVerticalSpacing(units.SMALL_SPACING)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def show_lines(self, lines):
        for line in self._labels:
            line.deleteLater()
        self._new_grid()
        self._labels = [pane_text(line) for line in lines]
        for line in self._labels:
            # Wrapped, a label in a left-packed grid takes its narrowest width and clips
            line.setWordWrap(False)
        self._columns = math.ceil(len(lines) / self.ROWS_PER_COLUMN)
        if not lines:
            return
        rows = math.ceil(len(lines) / self._columns)
        for number, line in enumerate(self._labels):
            self._grid.addWidget(line, number % rows, number // rows)

    def lines(self):
        return [line.text() for line in self._labels]

    def columns(self):
        return self._columns


class ReadingDetailsPane(QWidget):
    """A reading's Question, what it was, its layout on its ground beside its cards, its note"""

    open_requested = pyqtSignal(object)  # the reading's folder
    # The expand button was clicked, or Esc pressed while expanded: whether to expand
    expand_requested = pyqtSignal(bool)

    # The diagram's largest strip: as wide as the spread pane's, a short band tall
    DIAGRAM_STRIP = QSize(14 * units.GRID_UNIT, 8 * units.GRID_UNIT)
    # The note's widest, so its lines stay a readable length on a wide window
    NOTE_MEASURE = 45 * units.GRID_UNIT

    def __init__(self, parent=None):
        super().__init__(parent)
        self._details = None

        self.heading_label = typography.apply(pane_text(), typography.Role.HEADING_1, primary=True)
        self.meta_label = typography.apply(pane_text(), typography.Role.SMALL)
        self.meta_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        self.open_button = QPushButton(QIcon.fromTheme("document-open"), READINGS["library_open"])
        self.open_button.clicked.connect(self._on_open)

        heading_column = QVBoxLayout()
        heading_column.setContentsMargins(0, 0, 0, 0)
        heading_column.setSpacing(units.SMALL_SPACING)
        heading_column.addWidget(self.heading_label)
        heading_column.addWidget(self.meta_label)

        heading_row = QHBoxLayout()
        heading_row.setContentsMargins(0, 0, 0, 0)
        heading_row.setSpacing(units.LARGE_SPACING)
        heading_row.addLayout(heading_column, 1)
        heading_row.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignTop)

        # In the corner, after Open; its room is kept while hidden, so Open never shifts
        self._expanded = False
        self.expand_button = ExpandButton(
            READINGS["library_details_expand"], READINGS["library_details_restore"]
        )
        policy = self.expand_button.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.expand_button.setSizePolicy(policy)
        self.expand_button.clicked.connect(lambda: self.expand_requested.emit(not self._expanded))
        heading_row.addWidget(self.expand_button, 0, Qt.AlignmentFlag.AlignTop)

        self.diagram = LayoutDiagram(strip=self.DIAGRAM_STRIP)
        self.cards = _CardColumns()

        strip = QHBoxLayout()
        strip.setContentsMargins(0, 0, 0, 0)
        strip.setSpacing(units.GRID_UNIT)
        strip.addWidget(self.diagram, 0, Qt.AlignmentFlag.AlignTop)
        strip.addWidget(self.cards, 1, Qt.AlignmentFlag.AlignTop)

        self.note_rule = QFrame()
        self.note_rule.setFrameShape(QFrame.Shape.HLine)
        self.note_rule.setFrameShadow(QFrame.Shadow.Sunken)
        self.note_view = MarkdownView()
        self.note_view.setMaximumWidth(self.NOTE_MEASURE)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(units.LARGE_SPACING)
        body.addLayout(strip)
        body.addWidget(self.note_rule)
        body.addWidget(self.note_view)
        body.addStretch(1)
        content = QWidget()
        content.setLayout(body)

        # Everything under the heading scrolls as one, the diagram with the note
        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self._sync_expand_button)

        margin = units.GRID_UNIT
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, 2 * units.LARGE_SPACING, margin, units.LARGE_SPACING)
        layout.setSpacing(units.LARGE_SPACING)
        layout.addLayout(heading_row)
        layout.addWidget(self.scroll_area, 1)

    def details(self):
        """The ReadingRow shown, or None"""
        return self._details

    def is_expanded(self):
        return self._expanded

    def set_expanded(self, expanded):
        """Say whether the pane has the list's room; the Library tab gives it"""
        self._expanded = expanded
        self._sync_expand_button()

    def _sync_expand_button(self, *_):
        # Only a pane that doesn't fit needs it, so a short entry never shows it
        overflowing = self.scroll_area.verticalScrollBar().maximum() > 0
        self.expand_button.sync(self._expanded or overflowing, self._expanded)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._expanded:
            self.expand_requested.emit(False)
            return
        super().keyPressEvent(event)

    def card_lines(self):
        """The card rows' text, in reading order: down each column, then the next"""
        return self.cards.lines()

    def card_columns(self):
        return self.cards.columns()

    def show_details(self, row):
        previous, self._details = self._details, row
        if row is None:
            self.diagram.hide()
            return

        reading = row.reading
        self.heading_label.setText(label(reading))
        self.meta_label.setText(meta_text(row))
        self.open_button.setText(open_text(row))
        self.open_button.setIcon(QIcon.fromTheme(open_icon(row)))

        # A sandbox's order means nothing, so its marks go unnumbered
        numbered = not is_sandbox(reading)
        marks = reading_marks(reading, card_unit_size(), numbered=numbered)
        self.diagram.show_marks(layout_marks(marks, DIAGRAM.max_fill), drawn(reading.ground))

        self.cards.show_lines([card_row_text(card_row) for card_row in row.card_rows])

        note = _note_text(row.path)
        self.note_view.set_markdown(note, base=row.path)
        self.note_rule.setVisible(bool(note.strip()))
        self.note_view.setVisible(bool(note.strip()))

        if previous is None or previous.path != row.path:
            self.scroll_area.verticalScrollBar().setValue(0)
        self._sync_expand_button()

    def _on_open(self):
        if self._details is not None:
            self.open_requested.emit(self._details.path)
