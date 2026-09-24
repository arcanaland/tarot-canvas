"""The card Overview's notes section"""

from PyQt6.QtCore import QEvent, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.note_row_delegate import NoteRowDelegate
from tarot_canvas.ui.library.notes_model import NoteRole, NotesListModel
from tarot_canvas.ui.notes_text import text
from tarot_canvas.ui.palette import ghost_bar, subtle_fill
from tarot_canvas.ui.tabs.card_view.headings import SECTION_SCALE, apply_heading
from tarot_canvas.ui.tabs.card_view.passage_metrics import CORNER_RADIUS

MAX_ROWS = 3

PADDING = units.LARGE_SPACING

# Fractions of the ghost well's inner width
GHOST_TITLE_WIDTH = 0.40
GHOST_BODY_WIDTH = 0.85
GHOST_BAR_HEIGHT = 0.6  # of the font height of the line each bar stands in for


class ClickableWidget(QWidget):
    """A ghost"""

    clicked = pyqtSignal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(subtle_fill(self.palette()))
        painter.drawRoundedRect(QRectF(self.rect()), CORNER_RADIUS, CORNER_RADIUS)
        self.paint_contents(painter)
        painter.end()

    def paint_contents(self, painter):
        pass


class NoteRowsView(QListView):
    """A few of one card's notes as the shared note row, as tall as its rows."""

    noteActivated = pyqtSignal(str)  # the note's path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.list_model = NotesListModel(
            parent=self, card_in_subtitle=False, stub_preview=text("stub_note")
        )
        self.row_delegate = NoteRowDelegate(self, thumbnail=False)
        self.setModel(self.list_model)
        self.setItemDelegate(self.row_delegate)
        self.setUniformItemSizes(True)

        # Part of the page around it, not a box of its own
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.activated.connect(self._on_activated)

    def set_notes(self, notes):
        notes = list(notes)
        self.list_model.set_index({notes[0].card_id: notes} if notes else {})
        self._fit()

    def _fit(self):
        rows = self.list_model.rowCount()
        row_height = self.sizeHintForRow(0) if rows else 0
        self.setFixedHeight(rows * row_height + 2 * self.frameWidth())

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._fit()

    def _on_activated(self, index):
        note = index.data(NoteRole)
        if note is not None:
            self.noteActivated.emit(str(note.path))


class GhostRow(ClickableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("notes_section_ghost")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        metrics = QFontMetrics(self.font())
        self.setFixedHeight(2 * PADDING + 2 * metrics.height() + 2)

    def paint_contents(self, painter):
        inner = self.width() - 2 * PADDING
        if inner <= 0:
            return

        metrics = QFontMetrics(self.font())
        line = metrics.height()
        bar = line * GHOST_BAR_HEIGHT

        painter.setBrush(ghost_bar(self.palette()))
        y = PADDING
        for fraction in (GHOST_TITLE_WIDTH, GHOST_BODY_WIDTH):
            rect = QRectF(PADDING, y + (line - bar) / 2, inner * fraction, bar)
            painter.drawRoundedRect(rect, bar / 2, bar / 2)
            y += line + 2


class NotesSection(QWidget):
    """a heading, a [+] and note rows."""

    noteActivated = pyqtSignal(str)
    createRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("notes_section")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(units.SMALL_SPACING)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.heading = QLabel(text("section_heading"))
        self.heading.setObjectName("notes_section_heading")
        apply_heading(self.heading, SECTION_SCALE)
        self.heading.setVisible(bool(text("section_heading")))
        header.addWidget(self.heading)
        header.addStretch()

        self.new_button = QToolButton()
        self.new_button.setObjectName("notes_section_new")
        self.new_button.setText("+")
        self.new_button.setToolTip(text("new_note_tooltip"))
        self.new_button.clicked.connect(self.createRequested.emit)
        header.addWidget(self.new_button)

        layout.addLayout(header)

        self.ghost = GhostRow()
        self.ghost.clicked.connect(self.createRequested.emit)
        layout.addWidget(self.ghost)

        self.list_view = NoteRowsView()
        self.list_view.noteActivated.connect(self.noteActivated.emit)
        layout.addWidget(self.list_view)

        self.set_notes([])

    def set_notes(self, notes):
        """Show this card's notes, newest first or a ghost"""
        self.list_view.set_notes(notes[:MAX_ROWS])
        self.ghost.setVisible(not notes)
        self.list_view.setVisible(bool(notes))
