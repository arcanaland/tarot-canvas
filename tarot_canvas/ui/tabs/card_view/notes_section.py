"""The card Overview's notes section"""

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models import notes as notes_model
from tarot_canvas.ui.library import units
from tarot_canvas.ui.palette import ghost_bar, muted_text, subtle_fill, with_text_colour
from tarot_canvas.ui.tabs.card_view.headings import (
    SECTION_SCALE,
    SUBTITLE_SCALE,
    apply_heading,
)
from tarot_canvas.ui.tabs.card_view.notes_text import text
from tarot_canvas.ui.tabs.card_view.passage_metrics import CORNER_RADIUS
from tarot_canvas.utils.dates import relative_date_from_timestamp

MAX_ROWS = 3

PADDING = units.LARGE_SPACING
ROW_SPACING = units.SMALL_SPACING

# Fractions of the ghost well's inner width
GHOST_TITLE_WIDTH = 0.40
GHOST_BODY_WIDTH = 0.85
GHOST_BAR_HEIGHT = 0.6  # of the font height of the line each bar stands in for


class ElidedLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_full_text(self, value):
        self.full_text = value
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        metrics = QFontMetrics(self.font())
        self.setText(metrics.elidedText(self.full_text, Qt.TextElideMode.ElideRight, self.width()))


class ClickableWidget(QWidget):
    """A row or a ghost"""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

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


class NoteRow(ClickableWidget):
    def __init__(self, note, parent=None):
        super().__init__(parent)
        self.note = note
        self.setObjectName("notes_section_row")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        layout.setSpacing(0)

        title_font = QFont(self.font())
        title_font.setBold(bool(note.title) or note.first_line_is_heading)

        self.title_label = ElidedLabel()
        self.title_label.setObjectName("notes_section_row_title")
        self.title_label.setFont(title_font)
        self.title_label.set_full_text(note.title or note.first_line)
        layout.addWidget(self.title_label)

        self.date_label = ElidedLabel()
        self.date_label.setObjectName("notes_section_row_date")
        self.date_label.setFont(units.scaled_font(self.font(), SUBTITLE_SCALE))
        self.date_label.setPalette(with_text_colour(self.palette(), muted_text(self.palette())))
        self.date_label.set_full_text(relative_date_from_timestamp(note.modified))
        self.date_label.setVisible(bool(self.date_label.full_text))
        layout.addWidget(self.date_label)

        self.preview_label = ElidedLabel()
        self.preview_label.setObjectName("notes_section_row_preview")
        layout.addSpacing(units.SMALL_SPACING)
        preview = notes_model.first_body_line(note) if note.has_body else text("stub_note")
        self.preview_label.set_full_text(preview)
        self.preview_label.setVisible(bool(preview))
        layout.addWidget(self.preview_label)


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

        self.rows = QVBoxLayout()
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(ROW_SPACING)
        layout.addLayout(self.rows)

        self.set_notes([])

    def set_notes(self, notes):
        """Show this card's notes, newest first or a ghost"""
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        if not notes:
            ghost = GhostRow()
            ghost.clicked.connect(self.createRequested.emit)
            self.rows.addWidget(ghost)
            return

        for note in notes[:MAX_ROWS]:
            row = NoteRow(note)
            row.clicked.connect(lambda path=str(note.path): self.noteActivated.emit(path))
            self.rows.addWidget(row)
