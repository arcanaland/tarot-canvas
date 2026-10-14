import os
import random

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.settings import (
    BACKGROUND_COLOR_DEFAULT,
    BACKGROUND_COLOR_KEY,
    MOTION_LEVEL_DEFAULT,
    get_background_style,
    get_motion_level,
    get_settings,
)
from tarot_canvas.ui import commands, typography

# Import the refactored components
from tarot_canvas.ui.canvas import (
    CanvasIcon,
    DraggableCardItem,
    PannableGraphicsView,
    align_items_horizontally,
    align_items_vertically,
    arrange_items_in_circle,
    distribute_items_horizontally,
    distribute_items_vertically,
)
from tarot_canvas.ui.canvas.detail import (
    DETAIL_SETTLE_MS,
    DETAIL_VISIBLE_MARGIN,
    load_card_art,
)
from tarot_canvas.ui.canvas.motion import (
    AMBIENT_GAIN_FLOOR,
    MotionClock,
    approach,
    system_animations_enabled,
)
from tarot_canvas.ui.canvas.selection import GILT_ON_DARK, gilt_for_ground
from tarot_canvas.ui.canvas.view import MAX_ZOOM, MIN_ZOOM
from tarot_canvas.ui.card_transfer import card_from_mime, copy_card_to_clipboard, has_card
from tarot_canvas.ui.commands import Scope, tooltip_with_keys
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.utils.logger import logger


class CanvasTab(BaseTab):
    # Signal to notify the main window that we want to navigate
    navigation_requested = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.id = f"canvas_{id(self)}"
        self.tab_name = "Canvas"
        # Set once the clipboard's card has been pasted here, until the next copy
        self._clipboard_pasted = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.motion_clock = MotionClock(self)
        self.ambient_gain = 0.0

        self._cards = []
        self._top_z = 0.0
        self._bottom_z = 0.0
        self.motion_level = MOTION_LEVEL_DEFAULT
        self.desktop_wants_animation = True
        self.gilt = QColor(GILT_ON_DARK)

        self.setup_ui()
        self.deck = deck_manager.get_reference_deck()

        self.source_tab = None  # From where we came

        # Add multiple staggered calls to ensure window bounds
        # This creates a sequence of enforcement that is harder to override
        # TODO: another stinky code smell
        QTimer.singleShot(100, self.ensure_window_bounds)
        QTimer.singleShot(500, self.ensure_window_bounds)
        QTimer.singleShot(1000, self.ensure_window_bounds)

        QTimer.singleShot(100, self.update_tab_icon)

    def setup_ui(self):
        container = QWidget()
        main_layout = QHBoxLayout(container)

        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.scene = QGraphicsScene(self)

        # Set a more conservative scene rect size
        self.scene.setSceneRect(QRectF(-500, -500, 1000, 1000))

        # Use our custom view with middle-drag and shift+drag panning
        self.view = PannableGraphicsView(self.scene)
        self.view.card_dropped.connect(self.on_card_dropped)
        self.view.zoom_changed.connect(self._on_zoom_changed)

        # Sharpen the cards on screen once the camera settles
        self._detail_timer = QTimer(self)
        self._detail_timer.setSingleShot(True)
        self._detail_timer.setInterval(DETAIL_SETTLE_MS)
        self._detail_timer.timeout.connect(self.refresh_detail)
        self.view.zoom_changed.connect(self.schedule_detail)
        self.view.camera_moved.connect(self.schedule_detail)

        # Apply background from settings
        self.apply_background_settings()

        # Set sensible sizing policies for the view
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.view.setMinimumSize(400, 300)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Add canvas to layout (will take most of the space)
        main_layout.addWidget(self.view, 1)

        # Create toolbar on the right, showing the commands
        self.bind_commands()
        self.create_toolbar(main_layout)

        # Set up the base layout
        if hasattr(self, "layout"):
            # Clear any existing layout contents
            while self.layout.count():
                item = self.layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)

            # Reset margins to zero
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)
            self.layout.addWidget(container)
        else:
            # If BaseTab doesn't have a layout, create one
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(container)

    def apply_background_settings(self):
        """Apply background settings from preferences"""
        settings = get_settings()

        bg_style = get_background_style(settings)

        if bg_style == "checkerboard":
            ground = self.create_purple_checkerboard_background()
        elif bg_style == "gradient":
            ground = self.create_gradient_background()
        else:
            bg_color = settings.value(BACKGROUND_COLOR_KEY, BACKGROUND_COLOR_DEFAULT)
            ground = self.create_solid_color_background(bg_color)
        self.set_ground(ground)

        self.refresh_motion_settings()
        if self.motion_is_enabled() and self.isVisible():
            self.motion_clock.subscribe(self._advance_motion)
        else:
            self.motion_clock.unsubscribe(self._advance_motion)
            self.settle_motion()

    # Motion
    def refresh_motion_settings(self):
        self.motion_level = get_motion_level()
        self.desktop_wants_animation = system_animations_enabled()

    def motion_is_enabled(self):
        return self.motion_level != "Off"

    def reactive_is_allowed(self):
        return self.motion_level != "Off"

    def ambient_is_allowed(self):
        return (
            self.motion_level == "Full"
            and self.desktop_wants_animation
            and self.isVisible()
            and self.window().isActiveWindow()
        )

    def set_ground(self, color):
        """Pick the selection tone that shows up against this background colour."""
        self.gilt = gilt_for_ground(color)
        for card in self._cards:
            card.set_gilt(self.gilt)

    def _on_zoom_changed(self, view_scale):
        for card in self._cards:
            if card.isSelected():
                card.set_view_scale(view_scale)
        self.zoom_state_changed()

    def schedule_detail(self, *_):
        self._detail_timer.start()

    def refresh_detail(self):
        """Give each card the level of detail for how large it is on screen.

        Cards off screen are held to the level for 1x, so zooming into one card doesn't
        leave every other card on the canvas decoded at full size.
        """
        dpr = self.view.viewport().devicePixelRatioF() or 1.0
        zoom = abs(self.view.transform().m11())
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        margin_x = visible.width() * DETAIL_VISIBLE_MARGIN
        margin_y = visible.height() * DETAIL_VISIBLE_MARGIN
        near = visible.adjusted(-margin_x, -margin_y, margin_x, margin_y)
        for card in self._cards:
            on_screen = card.sceneBoundingRect().intersects(near)
            card.set_detail(dpr * (zoom if on_screen else min(zoom, 1.0)))

    def cards(self):
        """Every card on this canvas in no particular order."""
        return tuple(self._cards)

    def register_card(self, card):
        """Called by a card when it enters this tab's scene."""
        if card not in self._cards:
            self._cards.append(card)
            self.schedule_detail()

    def unregister_card(self, card):
        """Called by a card when it leaves this tab's scene."""
        if card in self._cards:
            self._cards.remove(card)

    def _advance_motion(self, t, dt):
        """Step every card on this canvas one frame"""
        self.ambient_gain = approach(
            self.ambient_gain, 1.0 if self.ambient_is_allowed() else 0.0, 8.0, dt
        )

        if self.ambient_gain < AMBIENT_GAIN_FLOOR:
            self.ambient_gain = 0.0

        view_scale = abs(self.view.transform().m11())
        for card in self._cards:
            card.advance_motion(t, dt, self.ambient_gain, view_scale)

    def settle_motion(self):
        """Put every card flat."""
        self.ambient_gain = 0.0
        for card in self._cards:
            card.settle_motion()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_motion_settings()
        if self.motion_is_enabled():
            self.motion_clock.subscribe(self._advance_motion)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.motion_clock.unsubscribe(self._advance_motion)
        self.settle_motion()

    def create_gradient_background(self):
        """Create a gradient background for the canvas"""
        center = QPointF(0, 0)
        radius = 800
        gradient = QRadialGradient(center, radius)

        gradient.setColorAt(0, QColor(50, 30, 80))  # Center - medium purple
        gradient.setColorAt(0.5, QColor(30, 18, 60))  # Middle - darker purple
        gradient.setColorAt(1, QColor(15, 10, 30))  # Edge - very dark purple

        brush = QBrush(gradient)
        self.scene.setBackgroundBrush(brush)
        self.view.setBackgroundBrush(brush)
        return gradient.stops()[0][1]

    def create_solid_color_background(self, color_str):
        """Create a solid color background for the canvas"""
        color = QColor(color_str)
        brush = QBrush(color)
        self.scene.setBackgroundBrush(brush)
        self.view.setBackgroundBrush(brush)
        return color

    def create_purple_checkerboard_background(self):
        """Create a purple checkerboard pattern background for the canvas"""
        light_purple = QColor(220, 210, 240)  # Light lavender
        dark_purple = QColor(180, 160, 220)  # Darker lavender

        size = 50  # Size of each square
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setPen(Qt.PenStyle.NoPen)

        painter.setBrush(QBrush(light_purple))
        painter.drawRect(0, 0, size, size)
        painter.drawRect(size, size, size, size)

        painter.setBrush(QBrush(dark_purple))
        painter.drawRect(0, size, size, size)
        painter.drawRect(size, 0, size, size)

        painter.end()

        pattern_brush = QBrush(pixmap)
        self.view.setBackgroundBrush(pattern_brush)
        return light_purple

    def ensure_window_bounds(self):
        """Ensure the window stays within screen boundaries"""
        window = self.window()
        if window:
            # Get screen geometry
            screen = QApplication.primaryScreen().availableGeometry()

            # Get window geometry
            window_geometry = window.geometry()

            # Check if window extends below screen
            if window_geometry.height() > screen.height() - 50:  # Leave 50px margin
                # Force a hard resize
                new_height = screen.height() - 100  # 100px margin for safety

                # Block signals temporarily to prevent resize events from triggering cascading changes
                window.blockSignals(True)
                window.resize(window_geometry.width(), new_height)
                window.blockSignals(False)

                print(f"Window height exceeds screen height - forcing resize to {new_height}")

                # Process events immediately to apply resize
                QApplication.processEvents()

            # Do a second check after processing events
            window_geometry = window.geometry()
            if window_geometry.bottom() > screen.bottom() - 50:
                # If still too tall, try a different approach - move to visible area
                print("Window still too tall, applying stronger constraints")

                # Move window to ensure it's within screen bounds
                new_y = max(screen.top(), screen.bottom() - window_geometry.height() - 50)
                window.move(window_geometry.x(), new_y)

                # Force immediate processing
                QApplication.processEvents()

                # As a last resort, modify maximum size of main window
                window.setMaximumHeight(screen.height() - 100)

    def bind_commands(self):
        self.commands = commands.bind(
            self,
            Scope.CANVAS,
            {
                "canvas.summon": self.on_draw_card,
                "canvas.flip": self.on_flip_card,
                "canvas.delete": self.on_delete_card,
                "canvas.bring_to_front": self.on_bring_to_front,
                "canvas.send_to_back": self.on_send_to_back,
                "canvas.align": self.on_align_cards,
                "canvas.fit": self.on_fit_view,
                "canvas.fullscreen": self.on_toggle_fullscreen,
                "canvas.cancel": self.on_escape_pressed,
            },
        )

    def on_escape_pressed(self):
        """Handle Escape key - leave fullscreen if in it, otherwise cancel selection"""
        if self.is_fullscreen():
            self.request_fullscreen_toggle()
            return
        for item in self.scene.selectedItems():
            item.setSelected(False)

    def supports_fullscreen(self):
        return True

    def fullscreen_focus_widget(self):
        return self.view

    def on_toggle_fullscreen(self):
        """Toggle canvas fullscreen. No-op when the tab has no main window."""
        self.request_fullscreen_toggle()

    def on_fullscreen_changed(self):
        """Keep the toolbar button in step with the actual fullscreen state"""
        full = self.is_fullscreen()
        self.fullscreen_action.setChecked(full)
        self.fullscreen_action.setToolTip(
            "Leave fullscreen (Esc)"
            if full
            else tooltip_with_keys("Fullscreen canvas", self.fullscreen_action)
        )

    def create_toolbar(self, parent_layout):
        """Create a vertical toolbar using QToolBar"""
        # Create a QToolBar configured for vertical layout
        self.toolbar = QToolBar()
        self.toolbar.setOrientation(Qt.Orientation.Vertical)
        self.toolbar.setIconSize(QSize(24, 24))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)

        # Primary actions group
        self.toolbar.addWidget(self.create_section_label("Cards"))

        # The toolbar's buttons are the commands', so each shows the key it has
        # Del is Edit > Delete's, which reaches the same handler
        for command_id, tooltip, keys in (
            ("canvas.summon", "Summon a random card", "canvas.summon"),
            ("canvas.flip", "Flip card", "canvas.flip"),
            ("canvas.delete", "Remove selected card", "window.delete"),
        ):
            action = self.commands[command_id]
            action.setToolTip(tooltip_with_keys(tooltip, keys))
            self.toolbar.addAction(action)

        # Paste
        self.paste_action = QAction(QIcon.fromTheme("edit-paste"), "Paste", self)
        self.paste_action.setToolTip(tooltip_with_keys("Paste card", "window.paste_card"))
        self.paste_action.triggered.connect(self.on_paste_card)
        self.toolbar.addAction(self.paste_action)
        QGuiApplication.clipboard().dataChanged.connect(self.on_clipboard_changed)
        self.update_paste_action()

        # Arrangement actions group
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.create_section_label("Arrange"))

        self.arrange_actions = {}
        for command_id, slot, tooltip in (
            ("canvas.bring_to_front", self.on_bring_to_front, "Bring card to front"),
            ("canvas.send_to_back", self.on_send_to_back, "Send card to back"),
            ("canvas.align", self.on_align_cards, "Align selected cards"),
        ):
            action = self.commands[command_id]
            action.setToolTip(tooltip_with_keys(tooltip, action))
            self.toolbar.addAction(action)
            self.arrange_actions[slot] = action

        # Grey out the arrangement buttons unless you select multiple cards
        self.scene.selectionChanged.connect(self.update_arrange_actions)
        self.scene.selectionChanged.connect(self.edit_state_changed)
        self.update_arrange_actions()

        # View control actions group
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.create_section_label("View"))

        # Zooming is View > Zoom's, whose keys are the window's
        for icon_name, slot, tooltip in (
            ("zoom-in", self.on_zoom_in, "Zoom in"),
            ("zoom-out", self.on_zoom_out, "Zoom out"),
        ):
            action = QAction(QIcon.fromTheme(icon_name), "", self)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            self.toolbar.addAction(action)

        fit_action = self.commands["canvas.fit"]
        fit_action.setToolTip("Fit all cards in view")
        self.toolbar.addAction(fit_action)

        reset_action = QAction(QIcon.fromTheme("zoom-original"), "", self)
        reset_action.setToolTip("Reset to default view")
        reset_action.triggered.connect(self.on_reset_view)
        self.toolbar.addAction(reset_action)

        self.fullscreen_action = self.commands["canvas.fullscreen"]
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.setToolTip(
            tooltip_with_keys("Fullscreen canvas", self.fullscreen_action)
        )
        self.toolbar.addAction(self.fullscreen_action)

        # Add the toolbar to the main layout
        parent_layout.addWidget(self.toolbar, 0)  # 0 means no stretch

    def create_section_label(self, text):
        """Create a section label for the toolbar"""
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #888; margin-top: 5px; margin-bottom: 2px;")
        typography.apply(label, typography.Role.SMALL)
        return label

    def on_draw_card(self):
        """Draw a random card from the selected deck in Card Explorer (or default deck)"""
        # Get the main window to access the card explorer
        main_window = self.window()
        if not main_window:
            print("Couldn't find main window")
            return

        # Try to find the card explorer in the main window
        selected_deck = None
        try:
            # Find card explorer in the main window
            card_explorer = None
            for child in main_window.findChildren(QWidget):
                if hasattr(child, "current_deck") and hasattr(child, "deck_selector"):
                    card_explorer = child
                    break

            # Get the currently selected deck from the explorer if it exists
            if card_explorer and card_explorer.current_deck:
                selected_deck = card_explorer.current_deck
        except Exception as e:
            print(f"Error accessing card explorer: {e}")

        # Use the selected deck or fall back to the default deck
        deck_to_use = selected_deck or self.deck
        if not deck_to_use:
            print("No deck available to draw from!")
            return

        # Get a random card from the selected deck
        card = deck_to_use.get_random_card()
        if not card:
            print(f"Could not draw a card from {deck_to_use.get_name()}!")
            return

        # Add a 50% chance for the card to be reversed
        is_reversed = random.choice([True, False])

        # Add the card, possibly reversed, using the selected deck
        self.add_specific_card(card, card_deck=deck_to_use, is_reversed=is_reversed)

        # Log what deck we drew from
        print(f"Drew card from {deck_to_use.get_name()} deck")

    def take_top_z(self):
        """The next depth above every card on the canvas."""
        self._top_z += 1.0
        return self._top_z

    def take_bottom_z(self):
        """The next depth below every card on the canvas."""
        self._bottom_z -= 1.0
        return self._bottom_z

    def cascade_from_occupied(self, pos, step=20, limit=20):
        """Nudge pos clear of a card already sitting there."""
        occupied = {(round(card.pos().x()), round(card.pos().y())) for card in self._cards}
        for _ in range(limit):
            if (round(pos.x()), round(pos.y())) not in occupied:
                break
            pos = QPointF(pos.x() + step, pos.y() + step)
        return pos

    # -- card clipboard and drop ---------------------------------------------

    def can_paste_card(self, mime):
        # Once per copy
        return has_card(mime) and not self._clipboard_pasted

    def paste_card(self, mime):
        item = self.place_card(mime)
        if item is not None:
            self._clipboard_pasted = True
            self.update_paste_action()
        return item

    def place_card(self, mime, at=None):
        """Resolve a card payload and place it; None if it names nothing installed"""
        resolved = card_from_mime(mime, deck_manager.get_all_decks())
        if resolved is None:
            logger.warning("Nothing placed: the card payload did not resolve")
            return None
        card, deck, is_reversed = resolved
        return self.add_specific_card(card, card_deck=deck, is_reversed=is_reversed, at=at)

    def selected_cards(self):
        return [item for item in self.scene.selectedItems() if isinstance(item, DraggableCardItem)]

    def can_copy_card(self):
        # The clipboard holds one card
        cards = self.selected_cards()
        return len(cards) == 1 and cards[0].deck is not None

    def copy_card(self):
        (item,) = self.selected_cards()
        copy_card_to_clipboard(item.card_data, item.deck, item.is_reversed())

    def can_cut_card(self):
        return self.can_copy_card()

    def cut_card(self):
        self.copy_card()
        self.on_delete_card()

    def can_delete(self):
        return bool(self.scene.selectedItems())

    def delete(self):
        self.on_delete_card()

    def can_select_all(self):
        return any(isinstance(item, DraggableCardItem) for item in self.scene.items())

    def select_all(self):
        for item in self.scene.items():
            if isinstance(item, DraggableCardItem):
                item.setSelected(True)

    def can_deselect(self):
        return bool(self.scene.selectedItems())

    def deselect(self):
        self.scene.clearSelection()

    def on_paste_card(self):
        mime = QGuiApplication.clipboard().mimeData()
        if self.can_paste_card(mime):
            self.paste_card(mime)

    # A real slot for Qt
    @pyqtSlot()
    def on_clipboard_changed(self):
        self._clipboard_pasted = False
        self.update_paste_action()

    def update_paste_action(self):
        self.paste_action.setEnabled(self.can_paste_card(QGuiApplication.clipboard().mimeData()))

    def on_card_dropped(self, mime, scene_pos):
        self.place_card(mime, at=scene_pos)

    def add_specific_card(self, card, card_deck=None, is_reversed=False, at=None):
        """Add a specific card to the canvas, optionally reversed"""
        # Load the card image
        image_path = card.get("image")
        if not image_path or not os.path.exists(image_path):
            print(f"Card image not found: {image_path}")
            return

        try:
            # The card is placed at a fitted size; sharper levels load as the view needs them
            art = load_card_art(image_path)
            if art is None:
                print(f"Failed to load image: {image_path}")
                return
            pixmap, source_size = art

            # Create a draggable card item
            card_item = DraggableCardItem(pixmap, card, self, deck=card_deck or self.deck)
            card_item.set_art_source(image_path, source_size)

            card_item.setZValue(self.take_top_z())

            # Set initial rotation based on reversed status
            card_item.set_orient(180 if is_reversed else 0)
            if card_item.card_data:
                card_item.card_data["reversed"] = is_reversed

            # Deselect any currently selected cards
            for selected_item in self.scene.selectedItems():
                selected_item.setSelected(False)

            # Place under the pointer (or middle of the view if it's in Narnia)
            target = at if at is not None else self.view.pointer_scene_pos()
            if target is None:
                target = self.view.mapToScene(self.view.viewport().rect().center())
                # slight nudge
                target = QPointF(
                    target.x() + random.randint(-50, 50), target.y() + random.randint(-50, 50)
                )
            pos = QPointF(target.x() - pixmap.width() / 2, target.y() - pixmap.height() / 2)
            pos = self.cascade_from_occupied(pos)
            card_item.setPos(pos)

            # Add the card to the scene
            self.scene.addItem(card_item)

            # Select the newly added card
            card_item.setSelected(True)

            # Pop in and spring back
            card_item.place_and_settle()

            reversed_status = "reversed" if is_reversed else "upright"
            print(f"Added card to canvas: {card['name']} ({reversed_status})")

            return card_item

        except Exception as e:
            print(f"Error adding card to canvas: {e}")
            return None

    def open_card_view(self, card_data):
        """Open a card view tab for the given card"""
        self.navigation_requested.emit(
            "open_card_view", {"card": card_data, "deck": self.deck, "source_tab_id": self.id}
        )

    # -- zoom --------------------------------------------------------------

    def can_zoom(self, how):
        scale = abs(self.view.transform().m11())
        if how == "in":
            return scale < MAX_ZOOM
        if how == "out":
            return scale > MIN_ZOOM
        # It also recentres on the cards, so there is always something to do
        return how == "reset"

    def zoom(self, how):
        {"in": self.on_zoom_in, "out": self.on_zoom_out, "reset": self.on_reset_view}[how]()

    # Canvas Control Methods
    def on_zoom_in(self):
        """Zoom into the canvas"""
        self.view.zoom_by_from_center(1.2)

    def on_zoom_out(self):
        """Zoom out of the canvas"""
        self.view.zoom_by_from_center(0.8)

    def on_fit_view(self):
        """Fit all items in view"""
        # Get bounding rect of all items
        items = self.scene.items()
        if not items:
            return
        # Calculate bounding rect of all items
        rect = items[0].sceneBoundingRect()
        for item in items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        # Add margin
        rect.adjust(-50, -50, 50, 50)
        # Fit view to rect
        self.view.fit_to_rect(rect)

    def on_reset_view(self):
        """Reset view to default position and zoom"""
        self.view.reset_zoom()
        # The scene rect moves with the camera now, so centre on the cards instead.
        items_rect = self.scene.itemsBoundingRect()
        self.view.centerOn(items_rect.center() if not items_rect.isNull() else QPointF(0, 0))
        self.view.grow_scene_rect()

    # Card Manipulation Methods
    def on_rotate_card(self):
        """Rotate the selected card by 90 degrees"""
        items = self.scene.selectedItems()
        for item in items:
            if isinstance(item, DraggableCardItem):
                item.set_orient(item.orient + 90)

    def on_flip_card(self):
        """Flip the selected card upside down (to indicate reversed position in Tarot)"""
        items = self.scene.selectedItems()
        for item in items:
            if isinstance(item, DraggableCardItem):
                new_rotation = 0 if item.is_reversed() else 180

                # Set the new rotation directly
                item.set_orient(new_rotation)

                # Update the card's internal state to reflect reversed status
                if hasattr(item, "card_data") and item.card_data:
                    # Toggle the reversed flag (create if it doesn't exist)
                    item.card_data["reversed"] = new_rotation == 180

    def on_delete_card(self):
        """Remove the selected card from canvas"""
        items = self.scene.selectedItems()
        for item in items:
            self.scene.removeItem(item)

    # Arrangement Control Methods
    def update_arrange_actions(self):
        """Enable the arrangement actions only when they have something to act on."""
        count = len(self.scene.selectedItems())
        for slot, action in self.arrange_actions.items():
            action.setEnabled(count >= (2 if slot == self.on_align_cards else 1))

    def on_bring_to_front(self):
        """Bring the selected cards to the front, keeping their order among themselves."""
        self._restack(self.scene.selectedItems(), self.take_top_z)

    def on_send_to_back(self):
        """Send the selected cards to the back, keeping their order among themselves."""
        self._restack(self.scene.selectedItems(), self.take_bottom_z, deepest_first=True)

    def raise_cards(self, cards):
        """Lift cards above every other card, as picking them up would."""
        moving = set(cards)
        others = [card.zValue() for card in self._cards if card not in moving]
        if not moving or not others:
            return
        if min(card.zValue() for card in moving) > max(others):
            return  # already on top; don't spend depth
        self._restack(moving, self.take_top_z)

    def _restack(self, items, allocate, deepest_first=False):
        """Give items a new depth while preserving their relative order."""
        cards = sorted(
            (item for item in items if isinstance(item, DraggableCardItem)),
            key=lambda item: item.zValue(),
            reverse=deepest_first,
        )

        for card in cards:
            card.setZValue(allocate())

    def on_align_cards(self):
        """Show alignment options for selected cards"""
        items = self.scene.selectedItems()
        # Only proceed if we have 2+ cards selected
        if len(items) < 2:
            return

        # Create a popup menu with alignment options
        menu = QMenu(self)

        # Horizontal alignment actions
        horizontal_menu = menu.addMenu("Horizontal Align")
        horizontal_menu.setIcon(QIcon.fromTheme("align-horizontal-left"))

        h_left = horizontal_menu.addAction("Left Edges")
        h_left.setIcon(QIcon.fromTheme("align-horizontal-left"))

        h_center = horizontal_menu.addAction("Centers")
        h_center.setIcon(QIcon.fromTheme("align-horizontal-center"))

        h_right = horizontal_menu.addAction("Right Edges")
        h_right.setIcon(QIcon.fromTheme("align-horizontal-right"))

        # Vertical alignment actions
        vertical_menu = menu.addMenu("Vertical Align")
        vertical_menu.setIcon(QIcon.fromTheme("align-vertical-top"))

        v_top = vertical_menu.addAction("Top Edges")
        v_top.setIcon(QIcon.fromTheme("align-vertical-top"))

        v_center = vertical_menu.addAction("Centers")
        v_center.setIcon(QIcon.fromTheme("align-vertical-center"))

        v_bottom = vertical_menu.addAction("Bottom Edges")
        v_bottom.setIcon(QIcon.fromTheme("align-vertical-bottom"))

        # Distribution options
        menu.addSeparator()

        distribute_h = menu.addAction("Distribute Horizontally")
        distribute_h.setIcon(QIcon.fromTheme("distribute-horizontal-center"))

        distribute_v = menu.addAction("Distribute Vertically")
        distribute_v.setIcon(QIcon.fromTheme("distribute-vertical-center"))

        # Circle arrangement (useful for tarot spread)
        menu.addSeparator()
        circle_arrange = menu.addAction("Arrange in Circle")
        circle_arrange.setIcon(QIcon.fromTheme("object-rotate-right"))

        # Connect actions to alignment functions
        h_left.triggered.connect(lambda: align_items_horizontally(items, "left"))
        h_center.triggered.connect(lambda: align_items_horizontally(items, "center"))
        h_right.triggered.connect(lambda: align_items_horizontally(items, "right"))

        v_top.triggered.connect(lambda: align_items_vertically(items, "top"))
        v_center.triggered.connect(lambda: align_items_vertically(items, "center"))
        v_bottom.triggered.connect(lambda: align_items_vertically(items, "bottom"))

        distribute_h.triggered.connect(lambda: distribute_items_horizontally(items))
        distribute_v.triggered.connect(lambda: distribute_items_vertically(items))

        circle_arrange.triggered.connect(lambda: arrange_items_in_circle(items))

        menu.exec(self.align_menu_anchor())

    def align_menu_anchor(self):
        """Global position for the align menu: just below its toolbar button."""
        button = self.toolbar.widgetForAction(self.arrange_actions[self.on_align_cards])
        if button is None:
            return QCursor.pos()
        return button.mapToGlobal(QPoint(0, button.height()))

    def update_tab_icon(self):
        """Update the tab with a canvas icon"""
        parent = self.parent()
        if parent:
            # Find the tab widget that contains this widget
            tab_widget = None
            parent_widget = parent

            # Try to find a parent that has setTabIcon method (likely a QTabWidget)
            while parent_widget and not tab_widget:
                if hasattr(parent_widget, "setTabIcon"):
                    tab_widget = parent_widget
                    break
                parent_widget = parent_widget.parent()

            # If we found a tab widget, update the tab icon
            if tab_widget:
                index = tab_widget.indexOf(self)
                if index >= 0:
                    # Create and set a canvas icon
                    canvas_icon = CanvasIcon()
                    tab_widget.setTabIcon(index, canvas_icon)
