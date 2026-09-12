"""Ask before downloading a deck from the catalog.

A dialog rather than an inline prompt: some reference decks' licences forbid commercial
use, and the reader should see the licence before the deck is on disk.
"""

from PyQt6.QtCore import QLocale, QPoint, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.catalog_client import deck_catalog
from tarot_canvas.ui.library.cover_cache import CoverCache
from tarot_canvas.ui.library.ghost_paint import paint_placeholder_well

# Adam's prose — every value is a placeholder
DOWNLOAD_TEXT = {
    "title": "[download dialog title]",
    "explanation": "[download dialog explanation]",
    "cancel_question": "[cancel download question: {name}]",
    "installed_toast": "[toast: {name} installed]",
    "failed: network": "[failed: network]",
    "failed: http": "[failed: http]",
    "failed: integrity": "[failed: integrity]",
    "failed: container": "[failed: container]",
    "failed: destination exists": "[failed: destination exists]",
    "failed: filesystem": "[failed: filesystem]",
    "failed: cancelled": "[failed: cancelled]",
}


def failure_text(failure):
    """What a failed tile says about its DownloadFailure"""
    return DOWNLOAD_TEXT[f"failed: {failure.kind.value}"]


class DeckDownloadDialog(QDialog):
    COVER_SIZE = QSize(160, 240)  # logical pixels, the library's 2:3 well
    HEADING_SCALE = 1.4
    CAPTION_SCALE = 0.85
    MINIMUM_WIDTH = 600

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(DOWNLOAD_TEXT["title"])
        self.setMinimumWidth(self.MINIMUM_WIDTH)

        self.cover = _Cover(deck_catalog().cover_path(entry), self.COVER_SIZE)

        self.heading_label = _index_text(entry.name)
        self.heading_label.setFont(
            units.scaled_font(self.heading_label.font(), self.HEADING_SCALE, bold=True)
        )

        self.explanation_label = _index_text(DOWNLOAD_TEXT["explanation"])

        self.artist_label = _index_text(entry.artist)
        self.size_label = _index_text(QLocale().formattedDataSize(entry.package_size))
        self.license_label = _index_text(entry.license)
        form = QFormLayout()
        form.addRow("Artist:", self.artist_label)
        form.addRow("Size:", self.size_label)
        form.addRow("License:", self.license_label)

        self.description_label = _index_text(entry.description)

        # A credit line, prose-length and repeating the artist and licence, so a caption
        # under the description rather than a form row
        self.attribution_label = _index_text(entry.attribution or "")
        self.attribution_label.setFont(
            units.scaled_font(self.attribution_label.font(), self.CAPTION_SCALE)
        )
        self.attribution_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        details = QVBoxLayout()
        details.setSpacing(units.LARGE_SPACING)
        details.addWidget(self.heading_label)
        details.addWidget(self.explanation_label)
        details.addSpacing(units.LARGE_SPACING)
        details.addLayout(form)
        details.addSpacing(units.LARGE_SPACING)
        details.addWidget(self.description_label)
        details.addWidget(self.attribution_label)
        details.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(units.GRID_UNIT)
        row.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(details, 1)

        buttons = QDialogButtonBox()
        self.download_button = buttons.addButton("Download", QDialogButtonBox.ButtonRole.AcceptRole)
        self.download_button.setIcon(QIcon.fromTheme("download"))
        self.cancel_button = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.download_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        margin = units.GRID_UNIT
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(units.GRID_UNIT)
        layout.addLayout(row)
        layout.addWidget(buttons)

        # Only once parented: showing a parentless label would open it as a window
        self.attribution_label.setVisible(entry.attribution is not None)

    def showEvent(self, event):
        super().showEvent(event)
        # Qt sizes a dialog from its hint, which can leave wrapped labels too little
        # height for the width it actually gets; they'd clip.
        needed = self.heightForWidth(self.width())
        if needed > self.height():
            self.resize(self.width(), needed)


def _index_text(text):
    label = QLabel(text)
    # The index is someone else's text: show it as written, never as markup
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class _Cover(QWidget):
    """The cover at a fixed size, or the library's placeholder well"""

    def __init__(self, path, size, parent=None):
        super().__init__(parent)
        self._path = path
        self._cache = CoverCache(capacity=4)
        self.setFixedSize(size)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pixmap = self._cache.get(self._path, self.size(), self.devicePixelRatioF())
        if pixmap is None:
            paint_placeholder_well(painter, self.rect(), self.palette())
        else:
            # Bottom-aligned with rounded corners and a hairline, as the library draws it
            art = QRect(QPoint(0, 0), pixmap.deviceIndependentSize().toSize())
            art.moveCenter(self.rect().center())
            art.moveBottom(self.rect().bottom())
            path = QPainterPath()
            path.addRoundedRect(QRectF(art), units.COVER_RADIUS, units.COVER_RADIUS)
            painter.setClipPath(path)
            painter.drawPixmap(art.topLeft(), pixmap)
            painter.setClipping(False)

            border = QColor(self.palette().text().color())
            border.setAlpha(units.COVER_BORDER_ALPHA)
            painter.setPen(border)
            painter.drawRoundedRect(art, units.COVER_RADIUS, units.COVER_RADIUS)
        painter.end()
