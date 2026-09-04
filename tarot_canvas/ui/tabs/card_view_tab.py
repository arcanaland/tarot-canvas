import os
from typing import ClassVar

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
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


def device_pixel_fit(source_size, available_width, available_height, dpr):
    """Device-pixel size at which to render `source_size` into a logical-pixel box.

    Widget geometry is in logical pixels, but on a scaled display the label paints
    width * dpr real pixels. Scaling a card to the logical size therefore hands Qt a
    pixmap it has to upscale at paint time, which is what makes the card look soft --
    at 200% it threw away half the resolution the source file already has.

    Caller must tag the result with setDevicePixelRatio(dpr) so layout still sees the
    logical size. The 1.0 cap keeps us from interpolating past one source pixel per
    device pixel.
    """
    width_scale = available_width * dpr / source_size.width()
    height_scale = available_height * dpr / source_size.height()
    scale = min(width_scale, height_scale, 1.0)
    return (
        max(1, round(source_size.width() * scale)),
        max(1, round(source_size.height() * scale)),
    )


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

        if card is None and self.deck:
            self.card = self.deck.get_random_card()

        # Set the tab name to the card name when it's created
        self.tab_name = self.card["name"] if self.card else "Card View"

        self.setup_ui()

        # Call update_tab_name() after initialization to set the tab's name immediately
        # Use a short timer to ensure the widget is fully added to its parent first
        QTimer.singleShot(100, self.update_tab_name)

    def setup_ui(self):
        """Set up the card view tab UI"""
        # We're already using the BaseTab's VBoxLayout
        main_layout = QVBoxLayout()

        if not self.deck or not self.card:
            self.layout.addWidget(QLabel("No deck or card available"))
            return

        # Create a splitter for image and information
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - card image in a container with reduced padding
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        # Reduce padding from 10px to 5px
        image_layout.setContentsMargins(5, 5, 5, 5)

        # Create an inner container to hold the image and allow vertical centering
        image_inner_container = QWidget()
        image_inner_layout = QVBoxLayout(image_inner_container)
        image_inner_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.image_label.setMinimumSize(1, 1)

        # Add image to inner container with stretches for vertical centering
        image_inner_layout.addStretch(1)
        image_inner_layout.addWidget(self.image_label)
        image_inner_layout.addStretch(1)

        # Add the inner container to the main image layout
        image_layout.addWidget(image_inner_container)

        # Add deck switching controls
        self.deck_switcher = DeckSwitcher(self)
        image_layout.addWidget(self.deck_switcher)

        # Create scroll area with proper sizing policy
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(image_container)
        self.scroll_area.setMinimumWidth(self.MIN_IMAGE_PANE_WIDTH)
        self.scroll_area.viewport().installEventFilter(self)

        # Load and display the image
        self.load_image()

        # Find compatible decks and update the deck switching UI
        self.deck_switcher.update_compatible_decks(self.card, self.deck, deck_manager)

        splitter.addWidget(self.scroll_area)

        # Right side - tabbed card information
        info_widget = QWidget()
        info_layout = QHBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)

        # Create tabbed widget for different information categories
        self.info_tabs = QTabWidget()
        self.info_tabs.setTabPosition(QTabWidget.TabPosition.East)  # Tabs on the right side

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

        # Add splitter to main layout
        main_layout.addWidget(splitter)

        # Set the main layout
        self.layout.addLayout(main_layout)

    def load_image(self):
        """Load and initially display the card image"""
        if (
            self.card
            and "image" in self.card
            and self.card["image"]
            and os.path.exists(self.card["image"])
        ):
            self.original_pixmap = QPixmap(self.card["image"])
            # Display the image at original size first
            self.image_label.setPixmap(self.original_pixmap)
            # Then schedule a resize
            QTimer.singleShot(50, self.resize_image)
        else:
            self.image_label.setText("No image available")
            self.original_pixmap = None

    def resize_image(self):
        """Resize the image to fit the available space while maintaining aspect ratio"""
        if not hasattr(self, "original_pixmap") or not self.original_pixmap:
            return

        # Get available width and height from scroll area
        if not hasattr(self, "scroll_area") or not self.scroll_area:
            return

        # Measure the viewport: the scroll area's own width includes the frame and
        # any scrollbar, and scaling to it is what makes the card overflow its pane.
        viewport = self.scroll_area.viewport()
        available_width = viewport.width() - 20  # 5px container padding each side
        available_height = viewport.height() - 20 - self.deck_switcher_height()

        dpr = viewport.devicePixelRatioF()

        if available_width <= 0 or available_height <= 0:
            return

        # Use reasonable default if dimensions are 0
        if self.original_pixmap.width() <= 0 or self.original_pixmap.height() <= 0:
            self.image_label.setPixmap(self.original_pixmap)
            return

        new_width, new_height = device_pixel_fit(
            self.original_pixmap.size(), available_width, available_height, dpr
        )

        # Create scaled pixmap
        scaled_pixmap = self.original_pixmap.scaled(
            new_width,
            new_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        scaled_pixmap.setDevicePixelRatio(dpr)

        # Apply to label
        self.image_label.setPixmap(scaled_pixmap)

    def deck_switcher_height(self):
        """Vertical space the deck switcher takes from the image, if it is shown"""
        if not hasattr(self, "deck_switcher") or not self.deck_switcher.isVisible():
            return 0
        return self.deck_switcher.sizeHint().height()

    def eventFilter(self, obj, event):
        """Rescale the card whenever the scroll area's viewport changes size"""
        if (
            hasattr(self, "scroll_area")
            and obj is self.scroll_area.viewport()
            and event.type() in (QEvent.Type.Resize, QEvent.Type.DevicePixelRatioChange)
        ):
            self.resize_image()
        return super().eventFilter(obj, event)

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
        self.scroll_area.setVisible(False)
        self.info_tabs.setVisible(False)

        # Update the current deck and card
        self.deck = new_deck
        self.card = new_card

        # Update the components
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
        self.scroll_area.setVisible(True)
        self.info_tabs.setVisible(True)
