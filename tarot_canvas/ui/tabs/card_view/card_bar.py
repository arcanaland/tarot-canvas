import math
import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QFontMetricsF, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from tarot_canvas.ui.card_transfer import deck_path_key


class TitleButton(QToolButton):
    """A flat, bold button that reads as a heading, eliding rather than pinning its pane wide"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title = ""
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        font = self.font()
        font.setBold(True)
        self.setFont(font)

    def title(self):
        return self._title

    def set_title(self, title):
        self._title = title
        self._elide()
        self.updateGeometry()

    def _chrome_width(self):
        """Everything in the button that isn't text: margins and the menu arrow"""
        return super().sizeHint().width() - self.fontMetrics().horizontalAdvance(self.text())

    def _title_width(self):
        # Rounded up: the integer advance can be a fraction short of the real
        # width, and elidedText then cuts a title it was given exactly the room for
        # (Noto Sans 10 bold: 154 px for 154.48, so the reference deck lost "ot")
        return math.ceil(QFontMetricsF(self.font()).horizontalAdvance(self._title))

    def sizeHint(self):
        # As wide as the whole title, whatever is showing now, so it can grow back
        hint = super().sizeHint()
        hint.setWidth(self._chrome_width() + self._title_width())
        return hint

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        room = max(0, self.width() - self._chrome_width())
        if room >= self._title_width():
            text = self._title
        else:
            text = self.fontMetrics().elidedText(self._title, Qt.TextElideMode.ElideRight, room)
        self.setText(text.replace("&", "&&"))  # a deck name is not a mnemonic


class DeckBar(QWidget):
    """Which deck's art is showing, above the card.

    Only worth a row when there is a choice: the tab hides it when a single deck
    has this card. The Overview pane names the deck either way. The menu shows
    this card as each deck draws it, so a deck is chosen by its art.
    """

    MAX_BUTTON_WIDTH = 240
    # Narrower than this and the name elides rather than pinning the pane wide
    MIN_BUTTON_WIDTH = 80
    THUMBNAIL_SIZE = QSize(40, 64)
    # Taller than this many rows and the list scrolls
    MAX_VISIBLE_ROWS = 6

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.compatible_decks = []
        self.current_index = 0

        self.deck_button = TitleButton()
        self.deck_button.setMinimumWidth(self.MIN_BUTTON_WIDTH)
        self.deck_button.setMaximumWidth(self.MAX_BUTTON_WIDTH)
        self.deck_button.setToolTip("Show this card from another deck ([ and ])")

        # A list inside the menu, not menu items: a list draws its icons at the
        # size it is given, where a menu item's icon size is the style's to pick
        self.deck_list = QListWidget()
        self.deck_list.setIconSize(self.THUMBNAIL_SIZE)
        self.deck_list.setFrameShape(QFrame.Shape.NoFrame)
        self.deck_list.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.deck_list.itemClicked.connect(self.on_item_chosen)
        self.deck_list.itemActivated.connect(self.on_item_chosen)

        self.deck_menu = QMenu(self.deck_button)
        list_action = QWidgetAction(self.deck_menu)
        list_action.setDefaultWidget(self.deck_list)
        self.deck_menu.addAction(list_action)
        self.deck_menu.aboutToShow.connect(self.fill_deck_list)
        self.deck_button.setMenu(self.deck_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # Centred over the card, not the pane's leading edge
        layout.addStretch()
        layout.addWidget(self.deck_button)
        layout.addStretch()

    def has_choice(self):
        return len(self.compatible_decks) > 1

    def update_decks(self, card, current_deck, deck_manager):
        """List every deck that has this card, current_deck selected."""
        card_id = card.get("id") if card else None
        self.compatible_decks = deck_manager.decks_containing(card_id) if card_id else []

        current = deck_path_key(current_deck.deck_path)
        current_index = next(
            (
                i
                for i, (deck, _) in enumerate(self.compatible_decks)
                if deck_path_key(deck.deck_path) == current
            ),
            None,
        )
        if current_index is None:
            # A deck opened from outside the library is still the one on screen
            self.compatible_decks.insert(0, (current_deck, card))
            current_index = 0

        self.current_index = current_index
        self.deck_button.set_title(current_deck.get_name())

    def fill_deck_list(self):
        """Built as the menu opens: stepping through cards shouldn't decode every deck's art"""
        self.deck_list.clear()
        for deck, card in self.compatible_decks:
            item = QListWidgetItem(self._thumbnail(card), deck.get_name())
            item.setToolTip(deck.get_name())
            self.deck_list.addItem(item)
        self.deck_list.setCurrentRow(self.current_index)

        rows = min(len(self.compatible_decks), self.MAX_VISIBLE_ROWS)
        row_height = self.deck_list.sizeHintForRow(0) if rows else 0
        self.deck_list.setMaximumHeight(rows * row_height + 2 * self.deck_list.frameWidth())
        self.deck_list.setFocus()

    def _thumbnail(self, card):
        image = card.get("image")
        if not image or not os.path.exists(image):
            return QIcon()
        size = self.THUMBNAIL_SIZE * self.devicePixelRatioF()
        pixmap = QPixmap(image).scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        pixmap.setDevicePixelRatio(self.devicePixelRatioF())
        return QIcon(pixmap)

    def on_item_chosen(self, item):
        self.deck_menu.hide()
        self.select(self.deck_list.row(item))

    def select(self, index):
        if not 0 <= index < len(self.compatible_decks):
            return
        new_deck, new_card = self.compatible_decks[index]
        if deck_path_key(new_deck.deck_path) == deck_path_key(self.tab.deck.deck_path):
            return
        self.tab.show_card(new_card, new_deck)

    def step(self, delta):
        """The same card in the previous or next deck, wrapping"""
        if self.has_choice():
            self.select((self.current_index + delta) % len(self.compatible_decks))


class CardBar(QToolBar):
    """What to do with the card on screen, below it.

    Triggers only. The keys stay on the window and the tab; an action here with a
    shortcut would bind its key twice, and Qt fires neither.
    """

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab

        self.setMovable(False)
        self.setFloatable(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        image_view = tab.image_view
        self.copy_action = self._add("edit-copy", "Copy", "Copy card (Ctrl+C)", tab.copy_card)

        # One button for the zoom state; the menu is the discoverable half of the
        # wheel, Ctrl+± and double-click. Text after a tab is only displayed.
        menu = QMenu(self)
        self.zoom_in_action = self._menu_item(menu, "Zoom In\tCtrl++", image_view.zoom_in)
        self.zoom_out_action = self._menu_item(menu, "Zoom Out\tCtrl+-", image_view.zoom_out)
        menu.addSeparator()
        self.fit_action = self._menu_item(menu, "Fit\tCtrl+0", image_view.reset_to_fit)
        self.native_action = self._menu_item(
            menu, "Actual Size\tDouble-click", image_view.zoom_to_native
        )
        self.zoom_button = QToolButton()
        self.zoom_button.setMenu(menu)
        self.zoom_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.zoom_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.zoom_button.setToolTip("Zoom")
        # As wide as the widest label, so the bar doesn't shift as the zoom changes
        self.zoom_button.setText("400%")
        self.zoom_button.setMinimumWidth(self.zoom_button.sizeHint().width())
        self.addWidget(self.zoom_button)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

        self.fullscreen_action = self._add(
            "view-fullscreen", "Fullscreen", "Fullscreen (F)", tab.request_fullscreen_toggle
        )
        self.fullscreen_action.setCheckable(True)
        self.info_pane_action = self._add(
            "sidebar-collapse-right", "Details", "Hide card details (I)", tab.toggle_info_pane
        )

        image_view.zoom_changed.connect(self.sync_zoom)
        self.sync_zoom()

    def _add(self, icon_name, text, tooltip, slot):
        """An icon-only action; text is what shows when the theme has no such icon."""
        action = QAction(QIcon.fromTheme(icon_name), text, self)
        action.setToolTip(tooltip)
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    def _menu_item(self, menu, text, slot):
        action = menu.addAction(text)
        action.triggered.connect(slot)
        return action

    # -- state the tab owns ------------------------------------------------

    def sync_zoom(self):
        view = self.tab.image_view
        if not view.has_image():
            self.zoom_button.setText("Fit")
            self.zoom_button.setEnabled(False)
            return
        self.zoom_button.setEnabled(True)
        at_fit = view.is_at_fit()
        percent = round(100 * view.current_scale() / view.native_scale())
        self.zoom_button.setText("Fit" if at_fit else f"{percent}%")
        self.zoom_out_action.setEnabled(not at_fit)
        self.fit_action.setEnabled(not at_fit)
        self.zoom_in_action.setEnabled(view.current_scale() < view.max_scale())

    def sync_fullscreen(self, full):
        self.fullscreen_action.setChecked(full)

    def sync_info_pane(self, is_open):
        """Say what the next press will do"""
        if is_open:
            self.info_pane_action.setIcon(QIcon.fromTheme("sidebar-collapse-right"))
            self.info_pane_action.setToolTip("Hide card details (I)")
        else:
            self.info_pane_action.setIcon(QIcon.fromTheme("sidebar-expand-right"))
            self.info_pane_action.setToolTip("Show card details (I)")
