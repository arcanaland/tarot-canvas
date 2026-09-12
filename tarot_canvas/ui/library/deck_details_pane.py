"""The library's details pane: one deck's cover, fields and credit line, and its one action.

Every deck gets one, installed or not. For a deck not yet downloaded, the licence sits above
the only Download button, so it is read before the deck is on disk.
"""

from dataclasses import replace

from PyQt6.QtCore import QLocale, QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.cover_cache import CoverCache
from tarot_canvas.ui.library.deck_downloads import DeckState
from tarot_canvas.ui.library.download_text import failure_text
from tarot_canvas.ui.library.ghost_paint import paint_placeholder_well
from tarot_canvas.ui.widgets.cover_banner import (
    BANNER_PADDING,
    BANNER_SUBTEXT,
    BANNER_TEXT,
    CoverBanner,
    is_readable_cover,
    set_banner_text,
)


class DeckDetailsPane(QWidget):
    open_requested = pyqtSignal(object)  # the TarotDeck
    download_requested = pyqtSignal(object)  # the CatalogEntry
    cancel_requested = pyqtSignal(str)  # the entry's slug

    HEADING_SCALE = 1.4
    CAPTION_SCALE = 0.85

    def __init__(self, parent=None):
        super().__init__(parent)
        self._details = None
        self._actions = None
        self.action_button = None
        self.progress_bar = None
        self.failure_label = None

        self.heading_label = _index_text()
        self.heading_label.setFont(
            units.scaled_font(self.heading_label.font(), self.HEADING_SCALE, bold=True)
        )
        self.artist_label = _index_text()
        self.header = _Header(self.heading_label, self.artist_label)

        self.version_label = _index_text()
        self.size_label = _index_text()
        self.license_label = _index_text()
        self.card_count_label = _index_text()
        self.form = QFormLayout()
        self.form.addRow("Version:", self.version_label)
        self.form.addRow("Size:", self.size_label)
        self.form.addRow("License:", self.license_label)
        self.form.addRow("Cards:", self.card_count_label)

        self.description_label = _index_text()
        # A credit line, prose-length and repeating the artist and licence, so a caption
        # under the description rather than a form row
        self.attribution_label = _index_text()
        self.attribution_label.setFont(
            units.scaled_font(self.attribution_label.font(), self.CAPTION_SCALE)
        )
        self.attribution_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        margin = units.GRID_UNIT
        body = QVBoxLayout()
        body.setContentsMargins(margin, 2 * units.LARGE_SPACING, margin, 0)
        body.setSpacing(units.LARGE_SPACING)
        body.addLayout(self.form)
        body.addSpacing(units.LARGE_SPACING)
        body.addWidget(self.description_label)
        body.addWidget(self.attribution_label)
        body.addStretch(1)

        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.header)
        column.addLayout(body, 1)

        # A long description scrolls; the action stays where it is
        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)

        self._action_area = QVBoxLayout()
        self._action_area.setContentsMargins(margin, margin, margin, margin)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.scroll_area, 1)
        layout.addLayout(self._action_area)

    def details(self):
        return self._details

    def show_details(self, details):
        previous, self._details = self._details, details

        # Progress alone moves the bar in place: a rebuild would drop a click on Cancel
        if previous is not None and replace(previous, progress=details.progress) == details:
            if self.progress_bar is not None:
                self.progress_bar.setValue(_percent(details.progress))
            return

        self._set_text(self.heading_label, details.name)
        self._set_text(self.artist_label, details.artist)
        self.header.set_cover_path(details.cover_path)
        self._set_row(self.version_label, details.version)
        size = None if details.size is None else QLocale().formattedDataSize(details.size)
        self._set_row(self.size_label, size)
        self._set_row(self.license_label, details.license)
        count = None if details.card_count is None else QLocale().toString(details.card_count)
        self._set_row(self.card_count_label, count)
        self._set_text(self.description_label, details.description)
        self._set_text(self.attribution_label, details.attribution)

        if previous is None or _identity(previous) != _identity(details):
            self.scroll_area.verticalScrollBar().setValue(0)
        if previous is None or _action_key(previous) != _action_key(details):
            self._rebuild_actions(details)
        elif self.progress_bar is not None:
            self.progress_bar.setValue(_percent(details.progress))

    def focus_action(self):
        if self.action_button is not None:
            self.action_button.setFocus(Qt.FocusReason.OtherFocusReason)

    @staticmethod
    def _set_text(label, text):
        label.setText(text or "")
        label.setVisible(text is not None)

    def _set_row(self, label, text):
        label.setText(text or "")
        self.form.setRowVisible(label, text is not None)

    # -- the action area --------------------------------------------------

    def _rebuild_actions(self, details):
        had_focus = self._actions is not None and self._actions.isAncestorOf(
            self.window().focusWidget()
        )
        if self._actions is not None:
            self._action_area.removeWidget(self._actions)
            self._actions.hide()
            # Later, not now: this can run inside the old button's own clicked
            self._actions.deleteLater()

        self._actions = QWidget()
        self.action_button = self.progress_bar = self.failure_label = None
        builders = {
            DeckState.INSTALLED: self._build_installed,
            DeckState.AVAILABLE: self._build_available,
            DeckState.DOWNLOADING: self._build_downloading,
            DeckState.FAILED: self._build_failed,
        }
        builders[details.state](details)
        self._action_area.addWidget(self._actions)
        # Now, not at the show Qt queues for a widget added to a visible parent, so the
        # button can take focus straight away
        self._actions.show()

        if had_focus:
            self.focus_action()

    # Open, Download and Try Again sit at the leading edge and Cancel at the trailing one,
    # so a double-click on Download can't land its second click on Cancel, nor the reverse.

    def _build_installed(self, _details):
        self.action_button = _button("Open", "document-open", self._on_open)
        row = _row(self._actions)
        row.addWidget(self.action_button)
        row.addStretch(1)

    def _build_available(self, _details):
        self.action_button = _button("Download", "download", self._on_download)
        row = _row(self._actions)
        row.addWidget(self.action_button)
        row.addStretch(1)

    def _build_downloading(self, details):
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(_percent(details.progress))
        self.action_button = _button("Cancel", "dialog-cancel", self._on_cancel)
        row = _row(self._actions)
        row.addWidget(self.progress_bar, 1)
        row.addWidget(self.action_button)

    def _build_failed(self, details):
        message = QFrame()
        message.setFrameShape(QFrame.Shape.StyledPanel)
        icon_label = QLabel()
        extent = self.style().pixelMetric(QStyle.PixelMetric.PM_ToolBarIconSize)
        icon_label.setPixmap(QIcon.fromTheme("dialog-error").pixmap(QSize(extent, extent)))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.failure_label = _index_text(failure_text(details.failure))
        inner = QHBoxLayout(message)
        inner.setSpacing(units.LARGE_SPACING)
        inner.addWidget(icon_label)
        inner.addWidget(self.failure_label, 1)

        self.action_button = _button("Try Again", "view-refresh", self._on_download)
        buttons = _row()
        buttons.addWidget(self.action_button)
        buttons.addStretch(1)

        column = QVBoxLayout(self._actions)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(units.LARGE_SPACING)
        column.addWidget(message)
        column.addLayout(buttons)

    # Read at click time, so a button outlives an update that changed only the entry object

    def _on_open(self):
        self.open_requested.emit(self._details.deck)

    def _on_download(self):
        self.download_requested.emit(self._details.entry)

    def _on_cancel(self):
        self.cancel_requested.emit(self._details.entry.slug)


def _identity(details):
    if details.deck is not None:
        return ("deck", details.deck.deck_path)
    return ("entry", details.entry.slug)


def _action_key(details):
    return (_identity(details), details.state, details.failure)


def _percent(progress):
    return round((progress or 0.0) * 100)


def _index_text(text=""):
    label = QLabel(text)
    # deck.toml and the index are someone else's text: show it as written, never as markup
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _button(text, icon_name, slot):
    button = QPushButton(QIcon.fromTheme(icon_name), text)
    button.clicked.connect(slot)
    return button


def _row(parent=None):
    row = QHBoxLayout(parent)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(units.LARGE_SPACING)
    return row


class _Header(QWidget):
    """The cover beside the name and artist, as the deck view's header lays it out expanded.

    The name and artist sit on the cover blurred into a band, which the cover hangs below.
    Without a readable cover there's no band, and the text keeps the palette's colours.
    """

    def __init__(self, heading, subheading, parent=None):
        super().__init__(parent)
        self._heading, self._subheading = heading, subheading
        self._path = None
        self._on_banner = False
        self._banner = CoverBanner(capacity=4)
        self.cover = _Cover(QSize(*units.cover_size(units.DENSITY_SMALL)))

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(units.SMALL_SPACING)
        text.addWidget(heading)
        text.addWidget(subheading)
        text.addStretch(1)

        row = QHBoxLayout(self)
        row.setContentsMargins(units.GRID_UNIT, BANNER_PADDING, units.GRID_UNIT, 0)
        row.setSpacing(units.LARGE_SPACING)
        row.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(text, 1)
        self._apply_banner_text()

    def set_cover_path(self, path):
        if path == self._path:
            return
        self._path = path
        self._on_banner = is_readable_cover(path)
        self.cover.set_path(path)
        self._apply_banner_text()
        self.update()

    def is_on_banner(self):
        return self._on_banner

    def banner_rect(self):
        """Full width, from the top to just under the artist, or the name if there's none"""
        if not self._on_banner:
            return QRect()
        last = self._heading if self._subheading.isHidden() else self._subheading
        bottom = last.mapTo(self, QPoint(0, last.height())).y()
        return QRect(0, 0, self.width(), bottom + BANNER_PADDING)

    def _apply_banner_text(self):
        on = self._on_banner
        set_banner_text(self._heading, on, BANNER_TEXT, QPalette.ColorRole.WindowText)
        set_banner_text(self._subheading, on, BANNER_SUBTEXT, QPalette.ColorRole.PlaceholderText)

    def paintEvent(self, event):
        rect = self.banner_rect()
        if not rect.isEmpty():
            painter = QPainter(self)
            self._banner.paint(painter, rect, self._path, self.devicePixelRatioF())
            painter.end()
        super().paintEvent(event)


class _Cover(QWidget):
    """The cover at a fixed size, or the library's placeholder well"""

    def __init__(self, size, parent=None):
        super().__init__(parent)
        self._path = None
        self._cache = CoverCache(capacity=4)
        self.setFixedSize(size)

    def set_path(self, path):
        if path != self._path:
            self._path = path
            self.update()

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
