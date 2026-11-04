from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.spreads import Spread
from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.canvas.tab_icon import DIAGRAM, layout_marks, spread_icon, spread_marks
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.pane_text import pane_text
from tarot_canvas.ui.strings import SPREADS
from tarot_canvas.ui.tabs.card_view.passage_metrics import body_html
from tarot_canvas.ui.widgets.deck_header import is_link, link_html


@dataclass(frozen=True)
class SpreadDetails:
    path: Path
    spread: Spread


def _section_title(text):
    return typography.apply(pane_text(text), typography.Role.HEADING_4)


def _rich_text(text):
    label = pane_text(text)
    label.setTextFormat(Qt.TextFormat.RichText)
    return label


# Between a credit's parts: Benebell Wen · Holistic Tarot
SOURCE_SEPARATOR = " · "


def _source_label(source):
    """One small, dim line of who and what, then its address: a credit, not a section"""
    words = [str(source[key]) for key in ("author", "name", "note") if source.get(key)]
    url = str(source.get("url", ""))
    if not is_link(url):
        words += [url] if url else []
        url = None
    label = _rich_text(link_html(SOURCE_SEPARATOR.join(words), [url] if url else []))
    typography.apply(label, typography.Role.SMALL)
    label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    return label


def _position_widgets(number, position):
    row = SPREADS["slot_row"].format(number=number, label=position.label).strip()
    yield pane_text(row)
    if position.meaning:
        meaning = pane_text(position.meaning)
        meaning.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        yield meaning


class SpreadDiagram(QWidget):
    """A spread's shape with its numbers, as large as its width and the pane's height allow"""

    WIDTH = 14 * units.GRID_UNIT

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon = None
        self.setFixedWidth(self.WIDTH)
        self.hide()

    def show_spread(self, spread):
        marks = layout_marks(
            spread_marks(spread, card_unit_size(), numbered=True), DIAGRAM.max_fill
        )
        self._icon = spread_icon(marks, DIAGRAM) if marks else None
        self.setVisible(self._icon is not None)
        self.update()

    def paintEvent(self, event):
        if self._icon is not None:
            painter = QPainter(self)
            self._icon.paint(painter, QRect(0, 0, self.width(), min(self.width(), self.height())))
            painter.end()


class SpreadDetailsPane(QWidget):
    edit_requested = pyqtSignal(object)  # the shown spread's folder

    def __init__(self, parent=None):
        super().__init__(parent)
        self._details = None

        self.heading_label = typography.apply(pane_text(), typography.Role.HEADING_1, primary=True)

        # On the title's line at the trailing edge, as the designer's pane has its menu
        self.edit_button = QToolButton()
        self.edit_button.setIcon(QIcon.fromTheme("document-edit"))
        self.edit_button.setText(SPREADS["edit"])
        self.edit_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.edit_button.setAutoRaise(True)
        self.edit_button.clicked.connect(self._on_edit)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(units.LARGE_SPACING)
        # A long name wraps before the button, which stays level with its first line
        title_row.addWidget(self.heading_label, 1)
        title_row.addWidget(self.edit_button, 0, Qt.AlignmentFlag.AlignTop)

        self.sections = QVBoxLayout()
        self.sections.setContentsMargins(0, 0, 0, 0)
        self.sections.setSpacing(units.SMALL_SPACING)

        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.addLayout(self.sections)
        column.addStretch(1)

        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)

        self.diagram = SpreadDiagram()

        body = QHBoxLayout()
        body.setSpacing(units.GRID_UNIT)
        body.addWidget(self.diagram)
        body.addWidget(self.scroll_area, 1)

        margin = units.GRID_UNIT
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, 2 * units.LARGE_SPACING, margin, units.LARGE_SPACING)
        layout.setSpacing(units.LARGE_SPACING)
        layout.addLayout(title_row)
        layout.addLayout(body, 1)

    def details(self):
        return self._details

    def show_details(self, details):
        previous, self._details = self._details, details
        self._clear_sections()
        if details is None:
            self.diagram.hide()
            return

        spread = details.spread
        self.diagram.show_spread(spread)
        self.heading_label.setText(spread.name or SPREADS["untitled"])

        if spread.description:
            self._add_section(
                SPREADS["description_title"], [_rich_text(body_html(spread.description))]
            )
        if spread.positions:
            rows = [
                widget
                for number, position in enumerate(spread.positions, start=1)
                for widget in _position_widgets(number, position)
            ]
            self._add_section(SPREADS["slots_title"], rows)
        if spread.sources:
            self._add_credits(map(_source_label, spread.sources))

        if previous is None or previous.path != details.path:
            self.scroll_area.verticalScrollBar().setValue(0)

    def _on_edit(self):
        if self._details is not None:
            self.edit_requested.emit(self._details.path)

    def section_labels(self):
        """Every label in the scrolling part, top to bottom"""
        items = (self.sections.itemAt(i).widget() for i in range(self.sections.count()))
        return [item for item in items if isinstance(item, QLabel)]

    def _add_section(self, title, widgets):
        if self.sections.count():
            self.sections.addSpacing(units.LARGE_SPACING)
        self.sections.addWidget(_section_title(title))
        for widget in widgets:
            self.sections.addWidget(widget)

    def _add_credits(self, widgets):
        """Last, under no heading"""
        if self.sections.count():
            self.sections.addSpacing(units.LARGE_SPACING)
        for widget in widgets:
            self.sections.addWidget(widget)

    def _clear_sections(self):
        while (item := self.sections.takeAt(0)) is not None:
            if item.widget() is not None:
                # Until it's deleted it would paint under the next section
                item.widget().hide()
                item.widget().deleteLater()
