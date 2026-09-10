import os
from typing import ClassVar

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.ui.tabs.card_view.color_dot import ColorDot
from tarot_canvas.ui.tabs.card_view.deck_switcher import DeckSwitcher
from tarot_canvas.ui.tabs.card_view.esoterica_tab import EsotericaTab
from tarot_canvas.ui.tabs.card_view.notes_tab import NotesTab
from tarot_canvas.ui.tabs.card_view.overview_tab import OverviewTab
from tarot_canvas.ui.widgets.overlay_button import OverlayButton
from tarot_canvas.ui.widgets.toast import Toast
from tarot_canvas.ui.widgets.zoomable_image_view import ZoomableImageView


class CardViewTab(BaseTab):
    # Signal to notify the main window that we want to navigate
    navigation_requested = pyqtSignal(str, object)

    # Define color mapping for card types and suits
    COLOR_MAP: ClassVar[dict] = {
        "major_arcana": "#916de4",  # Purple for Major Arcana
        "wands": "#ff9800",  # Orange for Wands
        "cups": "#2196f3",  # Blue for Cups
        "swords": "#ffeb3b",  # Yellow for Swords
        "pentacles": "#4caf50",  # Green for Pentacles
        "default": "#9e9e9e",  # Gray for unknown
    }

    # Smallest the image pane may become.
    MIN_IMAGE_PANE_WIDTH = 120

    def __init__(self, card=None, deck=None, source_tab_id=None, parent=None):
        super().__init__(parent)
        self.card = card
        self.deck = deck or deck_manager.get_reference_deck()
        self.deck_manager = deck_manager
        self.source_tab_id = source_tab_id
        self.id = f"card_{id(self)}"
        # How wide to bring the info pane back when it is toggled open
        self._info_pane_width = 0

        if card is None and self.deck:
            self.card = self.deck.get_random_card()

        # Set the tab name to the card name when it's created
        self.tab_name = self.card["name"] if self.card else "Card View"

        self.setup_ui()

        # Call update_tab_name() after initialization to set the tab's name immediately
        # Use a short timer to ensure the widget is fully added to its parent first
        # TODO: this seems terrible and is a massive code smell
        QTimer.singleShot(100, self.update_tab_name)

    def setup_ui(self):
        """Set up the card view tab UI"""
        main_layout = QVBoxLayout()

        if not self.deck or not self.card:
            self.layout.addWidget(QLabel("No deck or card available"))
            return

        self.splitter = splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - card image
        self.image_container = QWidget()
        image_layout = QVBoxLayout(self.image_container)
        image_layout.setContentsMargins(5, 5, 5, 5)

        self.image_view = ZoomableImageView(self)
        image_layout.addWidget(self.image_view, 1)

        self.exit_fullscreen_button = OverlayButton(
            self.image_view,
            "view-restore",
            "⛶",
            "Leave fullscreen (Esc)",
            self.request_fullscreen_toggle,
            row=0,
        )

        self.info_pane_button = OverlayButton(
            self.image_view,
            "sidebar-expand-right",
            "<",
            "Show card details (I)",
            self.toggle_info_pane,
            row=1,
        )
        self.toast = Toast(self.image_view)

        self.deck_switcher = DeckSwitcher(self)
        image_layout.addWidget(self.deck_switcher)

        self.image_container.setMinimumWidth(self.MIN_IMAGE_PANE_WIDTH)

        self.load_image()

        self.deck_switcher.update_compatible_decks(self.card, self.deck, deck_manager)

        self.setup_zoom_shortcuts()

        splitter.addWidget(self.image_container)

        # Right side - tabbed card information
        info_widget = QWidget()
        info_layout = QHBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)

        # A line the splitter handle sits
        # alone a draggable one.
        self.pane_seam = QFrame()
        self.pane_seam.setFrameShape(QFrame.Shape.VLine)
        self.pane_seam.setFrameShadow(QFrame.Shadow.Sunken)
        info_layout.addWidget(self.pane_seam)

        self.info_tabs = QTabWidget()

        # East on the normal view, but North for fullscreen
        self.info_tabs.setTabPosition(QTabWidget.TabPosition.East)

        # Tab 1: Overview
        self.overview_tab = OverviewTab(self.card, self.deck, self)
        self.info_tabs.addTab(self.overview_tab, "Overview")

        # Tab 2: Esoterica
        self.esoterica_tab = EsotericaTab(self.card, self)
        self.info_tabs.addTab(self.esoterica_tab, "Esoterica")

        # Tab 3: Notes
        self.notes_tab = NotesTab(self)
        self.info_tabs.addTab(self.notes_tab, "Notes")

        # Load the notes for this card
        self.notes_tab.load_card_notes(self.card)

        # Add the tabbed widget to the info layout
        info_layout.addWidget(self.info_tabs)

        splitter.addWidget(info_widget)

        # Set initial splitter sizes, and keep that 40/60 split as the window resizes
        splitter.setSizes([int(self.width() * 0.4), int(self.width() * 0.6)])
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        splitter.splitterMoved.connect(self.sync_info_pane_button)

        # Add splitter to main layout
        main_layout.addWidget(splitter)

        # Set the main layout
        self.layout.addLayout(main_layout)

    def load_image(self):
        """Load the card image into the zoomable view"""
        if (
            self.card
            and "image" in self.card
            and self.card["image"]
            and os.path.exists(self.card["image"])
        ):
            self.image_view.set_pixmap(QPixmap(self.card["image"]))
        else:
            self.image_view.set_message("No image available")

    def setup_zoom_shortcuts(self):
        """Zoom bindings, scoped to this tab and matching the canvas's vocabulary"""
        bindings = [
            ("Ctrl++", self.image_view.zoom_in),
            ("Ctrl+=", self.image_view.zoom_in),
            ("Ctrl+-", self.image_view.zoom_out),
            ("Ctrl+0", self.image_view.reset_to_fit),
            ("Ctrl+I", self.toggle_info_pane),
            ("Escape", self.on_escape_pressed),
        ]
        for key, slot in bindings:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

        for key, slot in (("F", self.request_fullscreen_toggle), ("I", self.toggle_info_pane)):
            shortcut = QShortcut(QKeySequence(key), self.image_view)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

    def on_escape_pressed(self):
        """Leave fullscreen if in it, otherwise put the card back at fit"""
        if self.is_fullscreen():
            self.request_fullscreen_toggle()
            return
        self.image_view.reset_to_fit()

    def fullscreen_focus_widget(self):
        return self.image_view

    def supports_fullscreen(self):
        return self.card is not None and self.deck is not None

    def enter_fullscreen(self):
        # isVisibleTo, not isVisible: the switcher hides itself when only one
        # deck has the card, and that state must survive fullscreen either way
        state = (
            self.splitter.sizes(),
            self.deck_switcher.isVisibleTo(self),
            (
                self.info_tabs.tabPosition(),
                self.info_tabs.documentMode(),
                self.info_tabs.tabBar().expanding(),
            ),
        )

        # Bring the pane back at the width it had, if it is asked for again
        self._info_pane_width = state[0][1] or self._info_pane_width
        self.deck_switcher.setVisible(False)
        self.splitter.setSizes([sum(state[0]), 0])

        # horizontal tabs
        self.info_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.info_tabs.setDocumentMode(True)
        self.info_tabs.tabBar().setExpanding(True)

        return state

    def exit_fullscreen(self, state):
        sizes, switcher_visible, tab_style = state
        self.deck_switcher.setVisible(switcher_visible)
        self.splitter.setSizes(sizes)
        position, document_mode, expanding = tab_style

        # switch tabs back to vertical
        self.info_tabs.setTabPosition(position)
        self.info_tabs.setDocumentMode(document_mode)
        self.info_tabs.tabBar().setExpanding(expanding)

    def info_pane_is_open(self):
        return self.splitter.sizes()[1] > 0

    def toggle_info_pane(self):
        """Show or hide the card details beside the artwork."""
        sizes = self.splitter.sizes()
        total = sum(sizes)

        if self.info_pane_is_open():
            self._info_pane_width = sizes[1]
            self.splitter.setSizes([total, 0])
        else:
            width = self._info_pane_width or int(total * 0.4)
            self.splitter.setSizes([max(self.MIN_IMAGE_PANE_WIDTH, total - width), width])

        self.sync_info_pane_button()

    def sync_info_pane_button(self):
        """Keep the button saying what the next press will do"""
        if self.info_pane_is_open():
            self.info_pane_button.set_icon("sidebar-collapse-right", ">")
            self.info_pane_button.setToolTip("Hide card details (I)")
        else:
            self.info_pane_button.set_icon("sidebar-expand-right", "<")
            self.info_pane_button.setToolTip("Show card details (I)")

    def on_fullscreen_changed(self):
        full = self.is_fullscreen()
        self.exit_fullscreen_button.setVisible(full)
        self.info_pane_button.setVisible(full)
        if full:
            self.sync_info_pane_button()
            self.toast.show_message("Press Esc to exit fullscreen")
        else:
            self.toast.dismiss()

    def update_tab_name(self):
        """Update the tab name and add color dot based on card type/suit"""
        if self.card:
            parent = self.parent()
            if parent:
                # Find the tab widget that contains this widget
                tab_widget = None
                parent_widget = parent

                # Try to find a parent that has setTabText method (likely a QTabWidget)
                while parent_widget and not tab_widget:
                    if hasattr(parent_widget, "setTabText"):
                        tab_widget = parent_widget
                        break
                    parent_widget = parent_widget.parent()

                # If we found a tab widget, update the tab text and icon
                if tab_widget:
                    index = tab_widget.indexOf(self)
                    if index >= 0:
                        # Update tab text
                        tab_widget.setTabText(index, self.card["name"])

                        # Create and set a colored dot icon based on card type/suit
                        color = self.get_card_color()
                        dot_icon = ColorDot(color)
                        tab_widget.setTabIcon(index, dot_icon)

                # If parent is a QStackedWidget inside a tab widget
                if hasattr(parent, "parent") and hasattr(parent.parent(), "setTabText"):
                    tab_widget = parent.parent()
                    index = tab_widget.indexOf(parent)
                    if index >= 0:
                        tab_widget.setTabText(index, self.card["name"])

                        # Create and set a colored dot icon based on card type/suit
                        color = self.get_card_color()
                        dot_icon = ColorDot(color)
                        tab_widget.setTabIcon(index, dot_icon)

    def get_card_color(self):
        """Get the appropriate color for this card based on its type/suit"""
        if not self.card:
            return self.COLOR_MAP["default"]

        card_type = self.card.get("type", "")

        if card_type == "major_arcana":
            return self.COLOR_MAP["major_arcana"]
        elif card_type == "minor_arcana":
            suit = self.card.get("suit", "")
            return self.COLOR_MAP.get(suit, self.COLOR_MAP["default"])
        else:
            return self.COLOR_MAP["default"]

    def navigate_back(self):
        """Navigate back to the source tab"""
        if self.source_tab_id:
            self.navigation_requested.emit("navigate", self.source_tab_id)

    def switch_to_deck(self, new_deck, new_card):
        """Switch to a different deck's version of the current card"""
        # Hide components during update
        self.image_container.setVisible(False)
        self.info_tabs.setVisible(False)

        # Update the current deck and card
        self.deck = new_deck
        self.card = new_card

        self.load_image()

        # Update the overview tab with the new card and deck info
        self.overview_tab.update_card_info(new_card, new_deck)

        # Update the notes tab for the new card
        self.notes_tab.load_card_notes(new_card)

        # Update the esoterica tab
        if hasattr(self.esoterica_tab, "update_card_info") and callable(
            getattr(self.esoterica_tab, "update_card_info", None)
        ):
            self.esoterica_tab.update_card_info(new_card)

        # Update the tab name in the parent tab widget
        self.update_tab_name()

        # Update deck switcher to reflect current selection
        self.deck_switcher.update_compatible_decks(new_card, new_deck, self.deck_manager)

        # Show components again
        self.image_container.setVisible(True)
        self.info_tabs.setVisible(True)
