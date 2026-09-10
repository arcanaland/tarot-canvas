import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QMenu,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QWidget,
)

from tarot_canvas.ui.card_transfer import deck_path_key


class DeckBar(QWidget):
    """Which deck's art is showing, above the card.

    Only worth a row when there is a choice: the tab hides it when a single deck
    has this card. The Overview pane names the deck either way.
    """

    # The combo is as wide as the longest deck name, to this cap
    MAX_COMBO_WIDTH = 240
    # Narrower than this and the name elides rather than pinning the pane wide
    MIN_COMBO_WIDTH = 80

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.compatible_decks = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.deck_combo = QComboBox()
        self.deck_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.deck_combo.setMinimumWidth(self.MIN_COMBO_WIDTH)
        self.deck_combo.setMaximumWidth(self.MAX_COMBO_WIDTH)
        self.deck_combo.setToolTip("Show this card from another deck ([ and ])")
        self.deck_combo.currentIndexChanged.connect(self.on_deck_selected)
        layout.addWidget(self.deck_combo)
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

        self.deck_combo.blockSignals(True)
        self.deck_combo.clear()
        for deck, _ in self.compatible_decks:
            self.deck_combo.addItem(deck.get_name(), os.fspath(deck.deck_path))
        self.deck_combo.setCurrentIndex(current_index)
        self.deck_combo.blockSignals(False)

    def on_deck_selected(self, index):
        if not 0 <= index < len(self.compatible_decks):
            return
        new_deck, new_card = self.compatible_decks[index]
        if deck_path_key(new_deck.deck_path) == deck_path_key(self.tab.deck.deck_path):
            return
        self.tab.show_card(new_card, new_deck)

    def step(self, delta):
        """The same card in the previous or next deck, wrapping"""
        if self.has_choice():
            count = self.deck_combo.count()
            self.deck_combo.setCurrentIndex((self.deck_combo.currentIndex() + delta) % count)


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
