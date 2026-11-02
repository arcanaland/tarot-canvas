from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from tarot_canvas.models.spreads import Spread
from tarot_canvas.ui import typography
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.notes_model import SUBTITLE_SEPARATOR
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


def _source_label(source):
    """One line of who and what, then its address"""
    words = [str(source[key]) for key in ("author", "note") if source.get(key)]
    url = str(source.get("url", ""))
    if not is_link(url):
        words += [url] if url else []
        url = None
    label = _rich_text(link_html(SUBTITLE_SEPARATOR.join(words), [url] if url else []))
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


class SpreadDetailsPane(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._details = None

        self.heading_label = typography.apply(pane_text(), typography.Role.HEADING_1, primary=True)

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

        margin = units.GRID_UNIT
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, 2 * units.LARGE_SPACING, margin, units.LARGE_SPACING)
        layout.setSpacing(units.LARGE_SPACING)
        layout.addWidget(self.heading_label)
        layout.addWidget(self.scroll_area, 1)

    def details(self):
        return self._details

    def show_details(self, details):
        previous, self._details = self._details, details
        self._clear_sections()
        if details is None:
            return

        spread = details.spread
        self.heading_label.setText(spread.name or SPREADS["untitled"])

        if spread.description:
            self._add_section(
                SPREADS["description_title"], [_rich_text(body_html(spread.description))]
            )
        if spread.sources:
            self._add_section(SPREADS["sources_title"], map(_source_label, spread.sources))
        if spread.positions:
            rows = [
                widget
                for number, position in enumerate(spread.positions, start=1)
                for widget in _position_widgets(number, position)
            ]
            self._add_section(SPREADS["slots_title"], rows)

        if previous is None or previous.path != details.path:
            self.scroll_area.verticalScrollBar().setValue(0)

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

    def _clear_sections(self):
        while (item := self.sections.takeAt(0)) is not None:
            if item.widget() is not None:
                # Until it's deleted it would paint under the next section
                item.widget().hide()
                item.widget().deleteLater()
