import os
from enum import Enum

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QComboBox, QSizePolicy, QToolBar, QWidget

from tarot_canvas.ui.card_transfer import deck_path_key


class BarPosition(Enum):
    HEADER = "header"
    FOOTER = "footer"


CARD_BAR_POSITION = BarPosition.FOOTER


def card_bar_position():
    """Dev override while the placement is being decided: TAROT_CANVAS_CARD_BAR=header."""
    value = os.environ.get("TAROT_CANVAS_CARD_BAR", "").lower()
    return BarPosition(value) if value in {p.value for p in BarPosition} else CARD_BAR_POSITION


class CardBar(QToolBar):
    """The card view's commands: which deck is showing, and what to do with the card.

    Triggers only. The keys stay on the window and the tab; an action here with a
    shortcut would bind its key twice, and Qt fires neither.
    """

    # The combo is as wide as the longest deck name, to this cap
    MAX_COMBO_WIDTH = 240

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.compatible_decks = []

        self.setMovable(False)
        self.setFloatable(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        self.prev_deck_action = self._add(
            "go-previous", "\N{BLACK LEFT-POINTING TRIANGLE}", "Previous deck", self.previous_deck
        )

        self.deck_combo = QComboBox()
        self.deck_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.deck_combo.currentIndexChanged.connect(self.on_deck_selected)
        self.addWidget(self.deck_combo)

        self.next_deck_action = self._add(
            "go-next", "\N{BLACK RIGHT-POINTING TRIANGLE}", "Next deck", self.next_deck
        )

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

        image_view = tab.image_view
        self.copy_action = self._add("edit-copy", "Copy", "Copy card (Ctrl+C)", tab.copy_card)
        self.zoom_out_action = self._add(
            "zoom-out", "\N{MINUS SIGN}", "Zoom out (Ctrl+-)", image_view.zoom_out
        )
        self.zoom_in_action = self._add("zoom-in", "+", "Zoom in (Ctrl++)", image_view.zoom_in)
        self.native_action = self._add(
            "zoom-original", "1:1", "Actual size (double-click)", image_view.zoom_to_native
        )
        self.fullscreen_action = self._add(
            "view-fullscreen", "Fullscreen", "Fullscreen (F)", tab.request_fullscreen_toggle
        )
        self.fullscreen_action.setCheckable(True)
        self.info_pane_action = self._add(
            "sidebar-collapse-right", "Details", "Hide card details (I)", tab.toggle_info_pane
        )

    def _add(self, icon_name, text, tooltip, slot):
        """An icon-only action; text is what shows when the theme has no such icon."""
        action = QAction(QIcon.fromTheme(icon_name), text, self)
        action.setToolTip(tooltip)
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    # -- deck --------------------------------------------------------------

    def update_decks(self, card, current_deck, deck_manager):
        """List every deck that has this card, current_deck selected.

        With one deck the combo still names it, disabled: the bar never hides.
        """
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

        # Fixed at the name's width: short of room, the toolbar moves icons into
        # its overflow menu rather than squeezing the one thing here that is text
        self.deck_combo.setFixedWidth(min(self.deck_combo.sizeHint().width(), self.MAX_COMBO_WIDTH))

        choice = len(self.compatible_decks) > 1
        for control in (self.deck_combo, self.prev_deck_action, self.next_deck_action):
            control.setEnabled(choice)

    def on_deck_selected(self, index):
        if not 0 <= index < len(self.compatible_decks):
            return
        new_deck, new_card = self.compatible_decks[index]
        if deck_path_key(new_deck.deck_path) == deck_path_key(self.tab.deck.deck_path):
            return
        self.tab.switch_to_deck(new_deck, new_card)

    def previous_deck(self):
        count = self.deck_combo.count()
        if count:
            self.deck_combo.setCurrentIndex((self.deck_combo.currentIndex() - 1) % count)

    def next_deck(self):
        count = self.deck_combo.count()
        if count:
            self.deck_combo.setCurrentIndex((self.deck_combo.currentIndex() + 1) % count)

    # -- state the tab owns ------------------------------------------------

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
