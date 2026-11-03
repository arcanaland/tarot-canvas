import math
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
    QWidget,
)

from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.models.spreads import Position, Spread, offsets_from_middle
from tarot_canvas.settings import (
    BACKGROUND_COLOR_DEFAULT,
    BACKGROUND_COLOR_KEY,
    CANVAS_TAB_MINIMAP_DEFAULT,
    CANVAS_TAB_MINIMAP_KEY,
    CHECKERBOARD_COLOR_DEFAULT,
    CHECKERBOARD_COLOR_KEY,
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
    SlotItem,
    align_items_horizontally,
    align_items_vertically,
    distribute_items_horizontally,
    distribute_items_vertically,
)
from tarot_canvas.ui.canvas.arc_popover import ARC_DEFAULTS, ArcPopover
from tarot_canvas.ui.canvas.detail import (
    DETAIL_SETTLE_MS,
    DETAIL_VISIBLE_MARGIN,
    card_unit_size,
    load_card_art,
)
from tarot_canvas.ui.canvas.ground import (
    CHECKERBOARD_SQUARE,
    GRADIENT_STOPS,
    checkerboard_partner,
)
from tarot_canvas.ui.canvas.motion import (
    AMBIENT_GAIN_FLOOR,
    MotionClock,
    approach,
    system_animations_enabled,
)
from tarot_canvas.ui.canvas.selection import GILT_ON_DARK, gilt_for_ground
from tarot_canvas.ui.canvas.tab_icon import (
    MINIMAP,
    card_marks,
    layout_marks,
    snapped,
    spread_icon,
)
from tarot_canvas.ui.canvas.view import MAX_ZOOM
from tarot_canvas.ui.card_transfer import (
    cards_from_mime,
    copy_card_to_clipboard,
    deck_path_key,
    has_card,
)
from tarot_canvas.ui.commands import Scope, set_tooltip_with_keys
from tarot_canvas.ui.strings import CANVAS, MAIN_WINDOW, SPREADS
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.utils.logger import logger

# Degrees a wheel notch turns a card, and with Alt held
WHEEL_TURN_STEP = 15
WHEEL_TURN_FINE_STEP = 1


def wheel_turn(orient, notches, fine):
    """Where notches of the wheel leave a card at orient.

    A fine notch turns 1°. A coarse one lands on a multiple of 15°, so from 7° one notch
    clockwise is 15°, not 22°.
    """
    if fine:
        return orient + notches * WHEEL_TURN_FINE_STEP
    steps = orient / WHEEL_TURN_STEP
    if math.isclose(steps, round(steps), abs_tol=1e-9):
        steps = round(steps)
    start = math.floor(steps) if notches > 0 else math.ceil(steps)
    return (start + notches) * WHEEL_TURN_STEP


class CanvasTab(BaseTab):
    # Signal to notify the main window that we want to navigate
    navigation_requested = pyqtSignal(str, object)
    # A card or its place on the canvas changed
    layout_changed = pyqtSignal()

    # The heading over the toolbar's first group
    TOOLS_TITLE = CANVAS["section_cards"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.id = f"canvas_{id(self)}"
        self.tab_name = CANVAS["tab_name"]
        # Set once the clipboard's card has been pasted here, until the next copy
        self._clipboard_pasted = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.motion_clock = MotionClock(self)
        self.ambient_gain = 0.0

        self._cards = []
        self._top_z = 0.0
        self._bottom_z = 0.0
        self.motion_level = MOTION_LEVEL_DEFAULT
        self.tab_minimap = CANVAS_TAB_MINIMAP_DEFAULT
        self.desktop_wants_animation = True
        self.gilt = QColor(GILT_ON_DARK)
        # Arrange on Arc starts from the last one this tab made
        self.arc_settings = dict(ARC_DEFAULTS)
        self.arc_popover = None
        # While the arc panel is open, nothing but it changes or selects a card
        self.arranging = False
        self._locked_actions = {}
        # Whether the view still follows the arc's preview, until it is moved by hand
        self._arc_following = False

        self._tab_marks = ()
        self._tab_icon = self.empty_tab_icon()
        self._tab_icon_timer = QTimer(self)
        self._tab_icon_timer.setSingleShot(True)
        self._tab_icon_timer.setInterval(0)
        self._tab_icon_timer.timeout.connect(self.refresh_tab_icon)

        self.setup_ui()
        self.deck = deck_manager.get_reference_deck()

        # Add multiple staggered calls to ensure window bounds
        # This creates a sequence of enforcement that is harder to override
        # TODO: another stinky code smell
        QTimer.singleShot(100, self.ensure_window_bounds)
        QTimer.singleShot(500, self.ensure_window_bounds)
        QTimer.singleShot(1000, self.ensure_window_bounds)

    def setup_ui(self):
        self.canvas_area = container = QWidget()
        main_layout = QHBoxLayout(container)

        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.scene = QGraphicsScene(self)

        # Set a more conservative scene rect size
        self.scene.setSceneRect(QRectF(-500, -500, 1000, 1000))

        # Use our custom view with middle-drag and shift+drag panning
        self.view = PannableGraphicsView(self.scene)
        self.view.card_dropped.connect(self.on_card_dropped)
        self.view.background_double_clicked.connect(self.on_draw_card)
        self.view.context_menu_requested.connect(self.on_context_menu_requested)
        self.view.card_turn_requested.connect(self.on_turn_card_by_wheel)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.camera_taken.connect(self._on_camera_taken)

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
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.addWidget(container)

    def apply_background_settings(self):
        """Apply background settings from preferences"""
        settings = get_settings()

        bg_style = get_background_style(settings)

        if bg_style == "checkerboard":
            colour = settings.value(CHECKERBOARD_COLOR_KEY, CHECKERBOARD_COLOR_DEFAULT)
            ground = self.create_checkerboard_background(colour)
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

        self.tab_minimap = settings.value(
            CANVAS_TAB_MINIMAP_KEY, CANVAS_TAB_MINIMAP_DEFAULT, type=bool
        )
        self.schedule_tab_icon()

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
            self.schedule_tab_icon()
            self.update_save_layout_action()

    def unregister_card(self, card):
        """Called by a card when it leaves this tab's scene."""
        if card in self._cards:
            self._cards.remove(card)
            self.schedule_tab_icon()
            self.update_save_layout_action()

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
        # Switched away from or closed, not minimised: the arc is abandoned
        if not event.spontaneous() and self.arc_is_open():
            self.arc_popover.cancel()
        self.motion_clock.unsubscribe(self._advance_motion)
        self.settle_motion()

    def create_gradient_background(self):
        """Create a gradient background for the canvas"""
        center = QPointF(0, 0)
        radius = 800
        gradient = QRadialGradient(center, radius)

        gradient.setStops(GRADIENT_STOPS)

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

    def create_checkerboard_background(self, color_str):
        """A checkerboard of the user's colour and its derived partner"""
        color = QColor(color_str)
        partner = checkerboard_partner(color)

        size = CHECKERBOARD_SQUARE
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setPen(Qt.PenStyle.NoPen)

        painter.setBrush(QBrush(color))
        painter.drawRect(0, 0, size, size)
        painter.drawRect(size, size, size, size)

        painter.setBrush(QBrush(partner))
        painter.drawRect(0, size, size, size)
        painter.drawRect(size, 0, size, size)

        painter.end()

        pattern_brush = QBrush(pixmap)
        self.view.setBackgroundBrush(pattern_brush)
        return color

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
        self.commands = commands.bind(self, Scope.CANVAS, self.command_handlers())

    def command_handlers(self):
        return {
            "canvas.summon": self.on_draw_card,
            "canvas.flip": self.on_flip_card,
            "canvas.rotate": self.on_rotate_card,
            "canvas.delete": self.on_delete_card,
            "canvas.bring_to_front": self.on_bring_to_front,
            "canvas.send_to_back": self.on_send_to_back,
            "canvas.align": self.on_align_cards,
            "canvas.save_layout_as_spread": self.on_save_layout_as_spread,
            "canvas.fit": self.on_fit_view,
            "canvas.fullscreen": self.on_toggle_fullscreen,
            "canvas.cancel": self.on_escape_pressed,
        }

    def tools(self):
        """The toolbar's first group, as (command, tooltip, whose key the tooltip shows)"""
        # Del is Edit > Delete's, which reaches the same handler
        return (
            ("canvas.summon", CANVAS["summon_tooltip"], "canvas.summon"),
            ("canvas.flip", CANVAS["flip_tooltip"], "canvas.flip"),
            ("canvas.rotate", CANVAS["rotate_tooltip"], "canvas.rotate"),
            ("canvas.delete", CANVAS["delete_tooltip"], "window.delete"),
        )

    def on_escape_pressed(self):
        """Handle Escape key - leave fullscreen if in it, otherwise cancel selection"""
        if self.arc_is_open():
            self.arc_popover.cancel()
            return
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
        if full:
            set_tooltip_with_keys(self.fullscreen_action, CANVAS["leave_fullscreen"], None)
        else:
            set_tooltip_with_keys(
                self.fullscreen_action, CANVAS["fullscreen_tooltip"], self.fullscreen_action
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
        self.toolbar.addWidget(self.create_section_label(self.TOOLS_TITLE))

        # The toolbar's buttons are the commands', so each shows the key it has
        for command_id, tooltip, keys in self.tools():
            action = self.commands[command_id]
            set_tooltip_with_keys(action, tooltip, keys)
            self.toolbar.addAction(action)

        # Paste
        self.paste_action = QAction(QIcon.fromTheme("edit-paste"), CANVAS["paste"], self)
        set_tooltip_with_keys(self.paste_action, CANVAS["paste_tooltip"], "window.paste_card")
        self.paste_action.triggered.connect(self.on_paste_card)
        self.toolbar.addAction(self.paste_action)
        QGuiApplication.clipboard().dataChanged.connect(self.on_clipboard_changed)
        self.update_paste_action()

        # Arrangement actions group
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.create_section_label(CANVAS["section_arrange"]))

        self.arrange_actions = {}
        for command_id, slot, tooltip in (
            ("canvas.bring_to_front", self.on_bring_to_front, CANVAS["bring_to_front_tooltip"]),
            ("canvas.send_to_back", self.on_send_to_back, CANVAS["send_to_back_tooltip"]),
            ("canvas.align", self.on_align_cards, CANVAS["align_tooltip"]),
        ):
            action = self.commands[command_id]
            set_tooltip_with_keys(action, tooltip, action)
            self.toolbar.addAction(action)
            self.arrange_actions[slot] = action

        save_layout = self.commands.get("canvas.save_layout_as_spread")
        if save_layout is not None:
            set_tooltip_with_keys(save_layout, SPREADS["save_layout_tooltip"], save_layout)
            self.toolbar.addAction(save_layout)
            self.update_save_layout_action()

        # Grey out the arrangement buttons unless you select multiple cards
        self.scene.selectionChanged.connect(self.update_arrange_actions)
        self.scene.selectionChanged.connect(self.edit_state_changed)
        self.update_arrange_actions()

        # View control actions group
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.create_section_label(CANVAS["section_view"]))

        # Zooming is View > Zoom's, whose keys are the window's
        for icon_name, slot, tooltip in (
            ("zoom-in", self.on_zoom_in, CANVAS["zoom_in_tooltip"]),
            ("zoom-out", self.on_zoom_out, CANVAS["zoom_out_tooltip"]),
        ):
            action = QAction(QIcon.fromTheme(icon_name), "", self)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            self.toolbar.addAction(action)

        fit_action = self.commands["canvas.fit"]
        fit_action.setToolTip(CANVAS["fit_tooltip"])
        self.toolbar.addAction(fit_action)

        reset_action = QAction(QIcon.fromTheme("zoom-original"), "", self)
        reset_action.setToolTip(CANVAS["reset_view_tooltip"])
        reset_action.triggered.connect(self.on_reset_view)
        self.toolbar.addAction(reset_action)

        self.fullscreen_action = self.commands["canvas.fullscreen"]
        self.fullscreen_action.setCheckable(True)
        set_tooltip_with_keys(
            self.fullscreen_action, CANVAS["fullscreen_tooltip"], self.fullscreen_action
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

    def on_draw_card(self, at=None):
        """Draw a random card from the selected deck in Card Explorer (or default deck),
        centred on at in scene coordinates, or under the pointer"""
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
        self.add_specific_card(card, card_deck=deck_to_use, is_reversed=is_reversed, at=at)

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
        return not self.arranging and has_card(mime) and not self._clipboard_pasted

    def paste_card(self, mime):
        item = self.place_card(mime)
        if item is not None:
            self._clipboard_pasted = True
            self.update_paste_action()
        return item

    def place_card(self, mime, at=None):
        """Resolve a card payload and place every card in it (cascading)

        Returns the first item placed
        """
        resolved = cards_from_mime(mime, deck_manager.get_all_decks())
        if not resolved:
            logger.warning("Nothing placed: the card payload did not resolve")
            return None
        return self.place_cards(resolved, at)

    def place_cards(self, resolved, at=None):
        """Place multiple cards"""
        placed = []
        for card, deck, is_reversed in resolved:
            if placed:
                # Where the last card was centered
                last = placed[-1]
                at = last.pos() + QPointF(last.pixmap().width() / 2, last.pixmap().height() / 2)
            item = self.add_specific_card(card, card_deck=deck, is_reversed=is_reversed, at=at)

            if item is not None:
                placed.append(item)

        # Each placement selected only itself
        for item in placed:
            item.setSelected(True)

        return placed[0] if placed else None

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
        return not self.arranging and self.can_copy_card()

    def cut_card(self):
        self.copy_card()
        self.on_delete_card()

    def can_delete(self):
        return not self.arranging and bool(self.scene.selectedItems())

    def delete(self):
        self.on_delete_card()

    def can_select_all(self):
        return not self.arranging and any(
            isinstance(item, DraggableCardItem) for item in self.scene.items()
        )

    def select_all(self):
        for item in self.scene.items():
            if isinstance(item, DraggableCardItem):
                item.setSelected(True)

    def can_deselect(self):
        return not self.arranging and bool(self.scene.selectedItems())

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
        if self.arranging:
            return
        self.paste_action.setEnabled(self.can_paste_card(QGuiApplication.clipboard().mimeData()))

    def on_card_dropped(self, mime, scene_pos):
        self.place_card(mime, at=scene_pos)

    def make_card_item(self, card, deck, reversed):
        """An item for card, not yet on the canvas, or None if its art won't load."""
        image_path = card.get("image")
        if not image_path or not os.path.exists(image_path):
            print(f"Card image not found: {image_path}")
            return None

        # The card is placed at a fitted size; sharper levels load as the view needs them
        art = load_card_art(image_path)
        if art is None:
            print(f"Failed to load image: {image_path}")
            return None
        pixmap, source_size = art

        card_item = DraggableCardItem(pixmap, card, self, deck=deck, reversed=reversed)
        card_item.set_art_source(image_path, source_size)
        return card_item

    def add_specific_card(self, card, card_deck=None, is_reversed=False, at=None):
        """Add a specific card to the canvas, optionally reversed"""
        try:
            card_item = self.make_card_item(card, card_deck or self.deck, is_reversed)
            if card_item is None:
                return None
            self._place_item(card_item, at)

            # Pop in and spring back
            card_item.place_and_settle()

            reversed_status = "reversed" if is_reversed else "upright"
            print(f"Added card to canvas: {card['name']} ({reversed_status})")

            return card_item

        except Exception as e:
            print(f"Error adding card to canvas: {e}")
            return None

    def add_slot(self, number, position_id, at=None, label="", meaning=""):
        """Add a slot, centred on at or under the pointer"""
        slot = SlotItem(number, position_id, self, label=label, meaning=meaning)
        self._place_item(slot, at)
        if at is None:
            slot.place_and_settle()
        return slot

    def _place_item(self, item, at):
        """Put item on top of the canvas, selected alone"""
        item.setZValue(self.take_top_z())

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
        item.setPos(self.cascade_from_occupied(target - item.boundingRect().center()))

        self.scene.addItem(item)
        item.setSelected(True)
        self.layout_changed.emit()

    def open_card_view(self, item):
        """Open a card view tab for the card on the canvas, from its own deck"""
        if isinstance(item, SlotItem):
            return
        self.navigation_requested.emit(
            "open_card_view", {"card": item.card_data, "deck": item.deck}
        )

    # -- context menu ------------------------------------------------------

    def card_at(self, scene_pos):
        """The topmost card at scene_pos, if any."""
        return self.view.card_at(scene_pos)

    def card_menu(self, scene_pos):
        """The menu for the card at scene_pos, or None. It selects the card if it wasn't."""
        item = self.card_at(scene_pos)
        if item is None:
            return None
        if not item.isSelected():
            self.scene.clearSelection()
            item.setSelected(True)
        return self.build_card_menu(item)

    def build_card_menu(self, item):
        menu = QMenu(self)
        open_action = menu.addAction(QIcon.fromTheme("document-open"), CANVAS["open_card"])
        open_action.triggered.connect(lambda: self.open_card_view(item))
        menu.addSeparator()
        menu.addAction(self.commands["canvas.flip"])
        menu.addAction(self.commands["canvas.rotate"])
        if len(self.selected_cards()) == 1:
            self._add_swap_menu(menu, item)
        menu.addSeparator()
        menu.addAction(self.commands["canvas.delete"])
        return menu

    def _add_swap_menu(self, menu, item):
        swap_menu = menu.addMenu(CANVAS["swap_deck"])
        current = deck_path_key(item.deck.deck_path) if item.deck else None
        card_id = item.card_data.get("id")
        others = 0
        for deck, card in deck_manager.decks_containing(card_id) if card_id else []:
            action = swap_menu.addAction(deck.get_name())
            if deck_path_key(deck.deck_path) == current:
                action.setCheckable(True)
                action.setChecked(True)
                action.setEnabled(False)
            else:
                others += 1
                action.triggered.connect(
                    lambda _checked=False, deck=deck, card=card: self.swap_card(item, deck, card)
                )
        swap_menu.setEnabled(others > 0)

    def on_context_menu_requested(self, scene_pos, global_pos):
        pressed = self.scene.mouseGrabberItem()
        if isinstance(pressed, DraggableCardItem):
            pressed.abandon_press()
        menu = self.card_menu(scene_pos)
        if menu is not None:
            menu.exec(global_pos)
            menu.deleteLater()

    def swap_card(self, item, deck, card):
        """Replace item with deck's art for card, in the same place and the same turn."""
        replacement = self.make_card_item(card, deck, item.is_reversed())
        if replacement is None:
            return None
        replacement.take_place_of(item)
        self.scene.removeItem(item)
        self.scene.addItem(replacement)
        replacement.setSelected(True)
        replacement.marks.settle()
        return replacement

    # -- zoom --------------------------------------------------------------

    def can_zoom(self, how):
        scale = abs(self.view.transform().m11())
        if how == "in":
            return scale < MAX_ZOOM
        if how == "out":
            return scale > self.view.min_zoom()
        # It also recentres on the cards, so there is always something to do
        return how == "reset"

    def zoom(self, how):
        {"in": self.on_zoom_in, "out": self.on_zoom_out, "reset": self.on_reset_view}[how]()

    # Canvas Control Methods
    def on_zoom_in(self):
        """Zoom into the canvas"""
        self._on_camera_taken()
        self.view.zoom_by_from_center(1.2)

    def on_zoom_out(self):
        """Zoom out of the canvas"""
        self._on_camera_taken()
        self.view.zoom_by_from_center(0.8)

    def on_fit_view(self):
        """Fit all items in view"""
        self._on_camera_taken()
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
        self._on_camera_taken()
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
        if items:
            self.layout_changed.emit()

    def on_turn_card_by_wheel(self, card, notches, fine):
        """Turn the cards a drag of card would move, each about its own centre."""
        for item in card.moving_cards():
            item.set_orient(wheel_turn(item.orient, notches, fine))
        self.layout_changed.emit()

    def on_flip_card(self):
        """Flip the selected card upside down (to indicate reversed position in Tarot)"""
        items = self.scene.selectedItems()
        for item in items:
            if isinstance(item, DraggableCardItem):
                item.set_reversed(not item.is_reversed())
        if items:
            self.layout_changed.emit()

    def on_delete_card(self):
        """Remove the selected card from canvas"""
        items = self.scene.selectedItems()
        for item in items:
            self.scene.removeItem(item)
        if items:
            self.layout_changed.emit()

    # Arrangement Control Methods
    def update_arrange_actions(self):
        """Enable the arrangement actions only when they have something to act on."""
        if self.arranging:
            return
        count = len(self.scene.selectedItems())
        for slot, action in self.arrange_actions.items():
            action.setEnabled(count >= (2 if slot == self.on_align_cards else 1))

    def on_bring_to_front(self):
        """Bring the selected cards to the front, keeping their order among themselves."""
        items = self.scene.selectedItems()
        self._restack(items, self.take_top_z)
        if items:
            self.layout_changed.emit()

    def on_send_to_back(self):
        """Send the selected cards to the back, keeping their order among themselves."""
        items = self.scene.selectedItems()
        self._restack(items, self.take_bottom_z, deepest_first=True)
        if items:
            self.layout_changed.emit()

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

    def update_save_layout_action(self):
        action = self.commands.get("canvas.save_layout_as_spread")
        if action is not None and not self.arranging:
            action.setEnabled(bool(self._cards))

    def layout_as_spread(self):
        """The cards as a spread of empty positions, numbered by z"""
        cards = sorted(self._cards, key=lambda card: card.zValue())
        centres = [card.pos() + card.boundingRect().center() for card in cards]
        offsets = offsets_from_middle([(c.x(), c.y()) for c in centres], card_unit_size().width())
        return Spread(
            positions=tuple(
                Position(id=f"p{number}", x=x, y=y, rotation=card.orient % 360, z=card.zValue())
                for number, (card, (x, y)) in enumerate(zip(cards, offsets, strict=True), start=1)
            )
        )

    def on_save_layout_as_spread(self):
        self.navigation_requested.emit("open_unsaved_spread", self.layout_as_spread())

    def arrange_order(self, items):
        """The order cards go round an arc: by z, as a layout numbers them"""
        return sorted(items, key=lambda item: item.zValue())

    def on_align_cards(self):
        """Show alignment options for selected cards"""
        items = self.scene.selectedItems()
        # Only proceed if we have 2+ cards selected
        if len(items) < 2:
            return

        # Create a popup menu with alignment options
        menu = QMenu(self)
        # The arc changes nothing until its popover's Apply
        menu.triggered.connect(lambda action: action is arc or self.layout_changed.emit())

        # Horizontal alignment actions
        horizontal_menu = menu.addMenu(CANVAS["align_horizontal"])
        horizontal_menu.setIcon(QIcon.fromTheme("align-horizontal-left"))

        h_left = horizontal_menu.addAction(CANVAS["align_left"])
        h_left.setIcon(QIcon.fromTheme("align-horizontal-left"))

        h_center = horizontal_menu.addAction(CANVAS["align_centers"])
        h_center.setIcon(QIcon.fromTheme("align-horizontal-center"))

        h_right = horizontal_menu.addAction(CANVAS["align_right"])
        h_right.setIcon(QIcon.fromTheme("align-horizontal-right"))

        # Vertical alignment actions
        vertical_menu = menu.addMenu(CANVAS["align_vertical"])
        vertical_menu.setIcon(QIcon.fromTheme("align-vertical-top"))

        v_top = vertical_menu.addAction(CANVAS["align_top"])
        v_top.setIcon(QIcon.fromTheme("align-vertical-top"))

        v_center = vertical_menu.addAction(CANVAS["align_centers"])
        v_center.setIcon(QIcon.fromTheme("align-vertical-center"))

        v_bottom = vertical_menu.addAction(CANVAS["align_bottom"])
        v_bottom.setIcon(QIcon.fromTheme("align-vertical-bottom"))

        # Distribution options
        menu.addSeparator()

        distribute_h = menu.addAction(CANVAS["distribute_horizontal"])
        distribute_h.setIcon(QIcon.fromTheme("distribute-horizontal-center"))

        distribute_v = menu.addAction(CANVAS["distribute_vertical"])
        distribute_v.setIcon(QIcon.fromTheme("distribute-vertical-center"))

        menu.addSeparator()
        arc = menu.addAction(CANVAS["arrange_arc"])
        arc.setIcon(QIcon.fromTheme("object-rotate-right"))

        # Connect actions to alignment functions
        h_left.triggered.connect(lambda: align_items_horizontally(items, "left"))
        h_center.triggered.connect(lambda: align_items_horizontally(items, "center"))
        h_right.triggered.connect(lambda: align_items_horizontally(items, "right"))

        v_top.triggered.connect(lambda: align_items_vertically(items, "top"))
        v_center.triggered.connect(lambda: align_items_vertically(items, "center"))
        v_bottom.triggered.connect(lambda: align_items_vertically(items, "bottom"))

        distribute_h.triggered.connect(lambda: distribute_items_horizontally(items))
        distribute_v.triggered.connect(lambda: distribute_items_vertically(items))

        if menu.exec(self.align_menu_anchor()) is arc:
            self.open_arc_popover()

    def open_arc_popover(self):
        """Arrange on Arc: the selected cards, previewed until Apply"""
        items = self.arrange_order(self.selected_cards())
        if len(items) < 2 or self.arc_is_open():
            return None
        if self.arc_popover is not None:
            self.arc_popover.deleteLater()
        self.arc_popover = popover = ArcPopover(
            items, self.arc_settings, self.view, self.canvas_area
        )
        popover.closed.connect(self._on_arc_closed)
        popover.applied.connect(self.layout_changed)
        popover.previewed.connect(self._follow_arc)
        self._arc_following = True
        self.set_arranging(True)
        popover.open()
        return popover

    def arc_is_open(self):
        return self.arc_popover is not None and not self.arc_popover.finished

    def _on_arc_closed(self, settings):
        self.arc_settings = settings
        self._arc_following = False
        self.set_arranging(False)

    def _on_camera_taken(self):
        self._arc_following = False

    def _follow_arc(self):
        if self._arc_following:
            popover = self.arc_popover
            self.keep_in_sight(popover.cards_rect(), popover.free_region())

    def keep_in_sight(self, rect, free):
        """Bring scene `rect` into `free`, a part of the viewport, moving the view as little as
        it can: nothing if it is there, a pan if it fits, else a zoom out. Never a zoom in."""
        rect = rect.adjusted(-50, -50, 50, 50)  # on_fit_view's margin
        if free.isEmpty():
            return
        shown = self.view.mapFromScene(rect).boundingRect()
        if free.contains(shown):
            return
        shrink = min(free.width() / shown.width(), free.height() / shown.height())
        if shrink < 1:
            self.view.zoom_by_from_center(shrink)
        # Put rect's centre at free's: move the viewport's centre by the difference
        scale = self.view.transform().m11()
        viewport_centre = QPointF(self.view.viewport().rect().center())
        offset = (viewport_centre - QPointF(free.center())) / scale
        self.view.grow_scene_rect()
        self.view.centerOn(rect.center() + offset)
        self.view.grow_scene_rect()

    def lockable_actions(self):
        """What can change or select a card, and so is off while the arc panel is open"""
        keep = {"canvas.fit", "canvas.fullscreen", "canvas.cancel"}
        actions = [action for name, action in self.commands.items() if name not in keep]
        return [*actions, self.paste_action]

    def set_arranging(self, arranging):
        """Lock the selection and the cards while the arc panel is open, and unlock them after"""
        if arranging == self.arranging:
            return
        self.arranging = arranging
        self.view.locked = arranging
        if arranging:
            self._locked_actions = {a: a.isEnabled() for a in self.lockable_actions()}
            for action in self._locked_actions:
                action.setEnabled(False)
        else:
            for action, enabled in self._locked_actions.items():
                action.setEnabled(enabled)
            self._locked_actions = {}
            self.update_arrange_actions()
            self.update_paste_action()
            self.update_save_layout_action()
        self.edit_state_changed()

    def align_menu_anchor(self):
        """Global position for the align menu: just below its toolbar button."""
        button = self.toolbar.widgetForAction(self.arrange_actions[self.on_align_cards])
        if button is None:
            return QCursor.pos()
        return button.mapToGlobal(QPoint(0, button.height()))

    def schedule_tab_icon(self):
        self._tab_icon_timer.start()

    def empty_tab_icon(self):
        """The tab icon when there are no marks to draw"""
        return CanvasIcon()

    def refresh_tab_icon(self):
        """Redraw the tab icon if the spread's snapped marks have changed"""
        marks = ()
        if self.tab_minimap:
            marks = snapped(layout_marks(card_marks(self._cards), MINIMAP.max_fill))
        if marks == self._tab_marks:
            return
        self._tab_marks = marks
        self._tab_icon = spread_icon(marks) if marks else self.empty_tab_icon()
        self.tab_label_changed.emit()

    def tab_title(self):
        return self.tab_name

    def rename_text(self):
        """What the rename dialog starts from"""
        return self.tab_name

    def rename_dialog_text(self):
        """The rename dialog's title and prompt"""
        return MAIN_WINDOW["rename_canvas"], MAIN_WINDOW["rename_canvas_prompt"]

    def rename(self, name):
        self.tab_name = name
        self.tab_label_changed.emit()

    def tab_icon(self):
        return self._tab_icon
