"""The library's details pane"""

from PyQt6.QtCore import QLocale, QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui import typography, units
from tarot_canvas.ui.catalog.downloads import DeckState
from tarot_canvas.ui.covers.cache import CoverCache
from tarot_canvas.ui.covers.ghost import paint_placeholder_well
from tarot_canvas.ui.strings import LIBRARY, failure_text, license_name
from tarot_canvas.ui.widgets.cover_banner import (
    BANNER_PADDING,
    BANNER_SUBTEXT,
    BANNER_TEXT,
    CoverBanner,
    is_readable_cover,
    set_banner_text,
)
from tarot_canvas.ui.widgets.inline_message import InlineMessage
from tarot_canvas.ui.widgets.pane_text import pane_form, pane_text


class DeckDetailsPane(QWidget):
    """The deck and its actions, then what a reader wants, then its metadata"""

    open_requested = pyqtSignal(object)  # the Deck
    download_requested = pyqtSignal(object)  # the CatalogEntry
    cancel_requested = pyqtSignal(str)  # the entry's slug
    menu_requested = pyqtSignal(object, object)  # the emptied QMenu to fill, the Deck

    def __init__(self, parent=None):
        super().__init__(parent)
        self._details = None
        self.action_button = None

        self.heading_label = typography.apply(pane_text(), typography.Role.HEADING_1, primary=True)
        self.artist_label = pane_text()

        # Cancel is away from Download, so a double click on Download can't land on it
        self.open_button = _button(LIBRARY["open"], "document-open", self._on_open)
        self.download_button = _button(LIBRARY["download"], "download", self._on_download)
        self.retry_button = _button(LIBRARY["try_again"], "view-refresh", self._on_download)
        self.cancel_button = _button(LIBRARY["cancel"], "dialog-cancel", self._on_cancel)
        self.menu_button = self._build_menu_button()

        actions = _row()
        actions.addWidget(self.open_button)
        actions.addWidget(self.download_button)
        actions.addWidget(self.retry_button)
        actions.addStretch(1)
        actions.addWidget(self.menu_button)
        self.header = _Header(self.heading_label, self.artist_label, actions)

        margin = units.GRID_UNIT
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.failure_message = InlineMessage(warning=True, closable=False)
        self.failure_label = self.failure_message.label
        self.failure_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # A download's progress or failure, across the pane
        self.status = QWidget()
        progress = _row()
        progress.addWidget(self.progress_bar, 1)
        progress.addWidget(self.cancel_button)
        status = QVBoxLayout(self.status)
        status.setContentsMargins(margin, units.LARGE_SPACING, margin, units.LARGE_SPACING)
        status.addLayout(progress)
        status.addWidget(self.failure_message)

        self.description_label = pane_text()

        self.card_count_label = pane_text()
        self.size_label = pane_text()
        self.license_label = pane_text()
        self.version_label = pane_text()
        self.form = pane_form()
        self.form.setSpacing(units.LARGE_SPACING)  # else it takes the body's
        self.form.addRow(LIBRARY["form_cards"], self.card_count_label)
        self.form.addRow(LIBRARY["form_size"], self.size_label)
        self.form.addRow(LIBRARY["form_license"], self.license_label)
        self.form.addRow(LIBRARY["form_version"], self.version_label)

        self.attribution_label = typography.apply(pane_text(), typography.Role.SMALL)
        self.attribution_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(margin, units.LARGE_SPACING, margin, margin)
        body.setSpacing(2 * units.LARGE_SPACING)
        body.addWidget(self.description_label)
        body.addLayout(self.form)
        body.addWidget(self.attribution_label)
        body.addStretch(1)

        # Only what is under the header scrolls
        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)
        self.scroll_area.setMinimumHeight(1)  # it gives way before the header does

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.status)
        layout.addWidget(self.scroll_area, 1)

        for widget in (*self._buttons(), self.progress_bar, self.status):
            widget.hide()

    def details(self):
        return self._details

    def show_details(self, details):
        previous, self._details = self._details, details

        self._set_text(self.heading_label, details.name)
        self._set_text(self.artist_label, details.artist)
        self.header.set_cover_path(details.cover_path)
        self._show_state(details)

        self._set_text(self.description_label, details.description)
        count = None if details.card_count is None else QLocale().toString(details.card_count)
        self._set_row(self.card_count_label, count)
        size = None if details.size is None else QLocale().formattedDataSize(details.size)
        self._set_row(self.size_label, size)
        self._set_row(self.license_label, license_name(details.license))
        self._set_row(self.version_label, details.version)
        self._set_text(self.attribution_label, details.attribution)

        if previous is None or _identity(previous) != _identity(details):
            self.scroll_area.verticalScrollBar().setValue(0)

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

    # -- the actions and a download's status ------------------------------

    def _buttons(self):
        return (
            self.open_button,
            self.menu_button,
            self.download_button,
            self.retry_button,
            self.cancel_button,
        )

    def _show_state(self, details):
        state = details.state
        installed = state is DeckState.INSTALLED
        downloading = state is DeckState.DOWNLOADING
        failed = state is DeckState.FAILED

        action = {
            DeckState.INSTALLED: self.open_button,
            DeckState.AVAILABLE: self.download_button,
            DeckState.DOWNLOADING: self.cancel_button,
            DeckState.FAILED: self.retry_button,
        }[state]
        changed = action is not self.action_button
        had_focus = changed and self.window().focusWidget() in self._buttons()
        self.action_button = action

        self.progress_bar.setValue(_percent(details.progress))
        self.progress_bar.setVisible(downloading)
        if failed:
            self.failure_message.show_message(failure_text(details.failure))
        else:
            self.failure_message.hide()
        self.status.setVisible(downloading or failed)

        action.show()
        # Before the old button hides, which would pass focus along
        if had_focus:
            self.focus_action()
        for button in self._buttons():
            button.setVisible(button is action or (installed and button is self.menu_button))

    def _build_menu_button(self):
        button = QToolButton()
        button.setIcon(QIcon.fromTheme("overflow-menu"))
        button.setToolTip(LIBRARY["deck_menu_tooltip"])
        button.setAccessibleName(LIBRARY["deck_menu_tooltip"])
        button.setAutoRaise(True)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        menu.aboutToShow.connect(lambda: self._on_menu_about_to_show(menu))
        button.setMenu(menu)
        return button

    def _on_open(self):
        self.open_requested.emit(self._details.deck)

    def _on_menu_about_to_show(self, menu):
        menu.clear()
        self.menu_requested.emit(menu, self._details.deck)

    def _on_download(self):
        self.download_requested.emit(self._details.entry)

    def _on_cancel(self):
        self.cancel_requested.emit(self._details.entry.slug)


def _identity(details):
    if details.deck is not None:
        return ("deck", details.deck.root_path)
    return ("entry", details.entry.slug)


def _percent(progress):
    return round((progress or 0.0) * 100)


def _button(text, icon_name, slot):
    button = QPushButton(QIcon.fromTheme(icon_name), text)
    button.clicked.connect(slot)
    return button


def _row():
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(units.LARGE_SPACING)
    return row


class _Header(QWidget):
    def __init__(self, heading, subheading, actions, parent=None):
        super().__init__(parent)
        self._heading, self._subheading = heading, subheading
        self._path = None
        self._on_banner = False
        self._banner = CoverBanner(capacity=4)
        self.cover = CoverWidget(QSize(*units.cover_size(units.DENSITY_SMALL)))

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(units.SMALL_SPACING)
        text.addWidget(heading)
        text.addWidget(subheading)
        # Clear of the band, and level with the cover's foot
        text.addSpacing(BANNER_PADDING + units.LARGE_SPACING)
        text.addStretch(1)
        text.addLayout(actions)

        row = QHBoxLayout(self)
        row.setContentsMargins(
            units.GRID_UNIT, BANNER_PADDING, units.GRID_UNIT, units.LARGE_SPACING
        )
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


class CoverWidget(QWidget):
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
