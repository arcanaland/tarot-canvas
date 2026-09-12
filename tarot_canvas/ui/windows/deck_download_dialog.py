"""Ask before downloading a deck from the catalog.

A dialog rather than an inline prompt: some reference decks' licences forbid commercial
use, and the reader should see the licence before the deck is on disk.
"""

from PyQt6.QtCore import QLocale, QSize, Qt
from PyQt6.QtGui import QFont, QPainter
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

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
    MINIMUM_WIDTH = 520

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(DOWNLOAD_TEXT["title"])
        self.setMinimumWidth(self.MINIMUM_WIDTH)

        self.cover = _Cover(deck_catalog().cover_path(entry), self.COVER_SIZE)

        self.heading_label = _index_text(entry.name)
        font = QFont(self.heading_label.font())
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * self.HEADING_SCALE)
        font.setBold(True)
        self.heading_label.setFont(font)

        self.explanation_label = _index_text(DOWNLOAD_TEXT["explanation"])

        self.artist_label = _index_text(entry.artist)
        self.size_label = _index_text(QLocale().formattedDataSize(entry.package_size))
        self.license_label = _index_text(entry.license)
        self.attribution_label = _index_text(entry.attribution or "")
        form = QFormLayout()
        form.addRow("Artist:", self.artist_label)
        form.addRow("Size:", self.size_label)
        form.addRow("License:", self.license_label)
        form.addRow("Attribution:", self.attribution_label)
        form.setRowVisible(self.attribution_label, entry.attribution is not None)

        self.description_label = _index_text(entry.description)

        details = QVBoxLayout()
        details.addWidget(self.heading_label)
        details.addWidget(self.explanation_label)
        details.addLayout(form)
        details.addWidget(self.description_label)
        details.addStretch(1)

        row = QHBoxLayout()
        row.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(details, 1)

        buttons = QDialogButtonBox()
        self.download_button = buttons.addButton("Download", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.download_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(buttons)


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
            # Bottom-aligned, as the library places it
            art = pixmap.deviceIndependentSize().toSize()
            painter.drawPixmap(
                (self.width() - art.width()) // 2, self.height() - art.height(), pixmap
            )
        painter.end()
