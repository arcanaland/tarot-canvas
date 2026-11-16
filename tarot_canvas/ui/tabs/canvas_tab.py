import logging
import math
import os
import random
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QWidget,
)

from tarot_canvas.models import backgrounds, readings
from tarot_canvas.models.deck_library import DeckLibrary, deck_library
from tarot_canvas.models.ground import drawn
from tarot_canvas.models.spreads import Position, Spread, offsets_from_middle
from tarot_canvas.settings import (
    CANVAS_GUIDES_DEFAULT,
    CANVAS_GUIDES_KEY,
    CANVAS_TAB_MINIMAP_DEFAULT,
    CANVAS_TAB_MINIMAP_KEY,
    MOTION_LEVEL_DEFAULT,
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
    image_ground,
    swirl,
)
from tarot_canvas.ui.canvas.arc_popover import ARC_DEFAULTS, ArcPopover
from tarot_canvas.ui.canvas.background_panel import COMMAND as BACKGROUND_COMMAND
from tarot_canvas.ui.canvas.background_panel import BackgroundPanel
from tarot_canvas.ui.canvas.detail import (
    DETAIL_SETTLE_MS,
    DETAIL_VISIBLE_MARGIN,
    card_unit_size,
    load_card_art,
)
from tarot_canvas.ui.canvas.ground import (
    CHECKERBOARD_SQUARE,
    GROUND_HUE_DEFAULT,
    GROUND_HUES,
    ground_hue,
    shadow_for_ground,
)
from tarot_canvas.ui.canvas.ground_paint import AURA_RADIUS, aura_gradient, checkerboard_tile
from tarot_canvas.ui.canvas.guides import GuideItem
from tarot_canvas.ui.canvas.motion import (
    AMBIENT_GAIN_FLOOR,
    SHADOW_OPACITY,
    MotionClock,
    Pace,
    approach,
    system_animations_enabled,
)
from tarot_canvas.ui.canvas.saved_canvas import (
    SavedCanvasPane,
    cards_of,
    new_reading,
    resolve_decks,
)
from tarot_canvas.ui.canvas.saved_reading import SavedReading
from tarot_canvas.ui.canvas.selection import GILT_ON_DARK, gilt_for_ground
from tarot_canvas.ui.canvas.tab_icon import (
    MINIMAP,
    card_marks,
    layout_marks,
    snapped,
    spread_icon,
)
from tarot_canvas.ui.canvas.view import HOME_MARGIN, MAX_ZOOM
from tarot_canvas.ui.card_transfer import (
    cards_from_mime,
    copy_card_to_clipboard,
    has_card,
)
from tarot_canvas.ui.commands import Scope, set_tooltip_with_keys
from tarot_canvas.ui.strings import CANVAS, MAIN_WINDOW, READINGS, SPREADS
from tarot_canvas.ui.tabs.base_tab import BaseTab

log = logging.getLogger(__name__)

# A tab title longer than this many average characters is cut short
TAB_TITLE_CHARS = 32

# Degrees a wheel notch turns a card, and with Alt held
WHEEL_TURN_STEP = 15
WHEEL_TURN_FINE_STEP = 1

# Background factory: each draws a Ground of its style
GROUNDS = {
    "checkerboard": lambda tab, ground: tab.create_checkerboard_background(
        ground.checkerboard_color
    ),
    "gradient": lambda tab, ground: tab.create_gradient_background(ground_hue(ground)),
    "solid": lambda tab, ground: tab.create_solid_color_background(ground.color),
    "swirl": lambda tab, ground: tab.create_swirl_background(ground_hue(ground)),
    "image": lambda tab, ground: tab.create_image_background(
        ground.image, ground.positioning, ground.fill
    ),
}


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
    # The default ground in Preferences was changed from this tab
    default_ground_changed = pyqtSignal()

    # The heading over the toolbar's first group
    TOOLS_TITLE = CANVAS["section_cards"]
    # What add_slot puts on the canvas
    SLOT_ITEM = SlotItem
    # Whether Save makes this a saved canvas; a tab that saves something else says no
    SAVES_CANVAS = True
    # Whether the tab can have a ground of its own, which only a tab that keeps one offers
    OWN_GROUND = True
    # The ground menu's entry for canvas.summon, which places at the click
    DRAW_HERE = CANVAS["draw_here"]
    # Set once the canvas is a reading
    saved_reading = None

    def __init__(self, parent=None):
        super().__init__(parent)
        # The tab's own Ground, or None while it follows the default in Preferences
        self.ground = None
        self.background_panel = None
        self.id = f"canvas_{id(self)}"
        self.tab_name = CANVAS["tab_name"]
        # Whether the user manually named the tab
        self.named_by_hand = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.motion_clock = MotionClock(self)
        self.ambient_gain = 0.0
        # How fast the ground moves on its own
        self.ground_pace = Pace()

        self._cards = []
        # A kept reading's cards that its decks could not lay out, written back as they were read
        self.unrestored = []
        self._top_z = 0.0
        self._bottom_z = 0.0
        self.motion_level = MOTION_LEVEL_DEFAULT
        self.tab_minimap = CANVAS_TAB_MINIMAP_DEFAULT
        # Whether a dragged card snaps to the cards around it
        self.snap_guides = CANVAS_GUIDES_DEFAULT
        # In the scene only while a card is being dragged
        self.guide_item = GuideItem()
        self.desktop_wants_animation = True
        self.gilt = QColor(GILT_ON_DARK)
        self.shadow_tone = (QColor(Qt.GlobalColor.black), SHADOW_OPACITY)
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
        self.deck = deck_library.reference()

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
        self.apply_ground()

        self.refresh_motion_settings()
        if self.motion_is_enabled() and self.isVisible():
            self.motion_clock.subscribe(self._advance_motion)
        else:
            self.motion_clock.unsubscribe(self._advance_motion)
            self.settle_motion()

        self.tab_minimap = settings.value(
            CANVAS_TAB_MINIMAP_KEY, CANVAS_TAB_MINIMAP_DEFAULT, type=bool
        )
        self.snap_guides = settings.value(CANVAS_GUIDES_KEY, CANVAS_GUIDES_DEFAULT, type=bool)
        self.schedule_tab_icon()

    def drawn_ground(self):
        """The tab's own ground, else the default; the default too while its image is missing"""
        return drawn(self.ground, get_settings())

    def apply_ground(self):
        """Draw the tab's own ground, or the default when it has none"""
        ground = self.drawn_ground()

        # swirl has an object we need to keep alive
        if ground.style != "swirl":
            self._drop_swirl()
        if self.view.backdrop is not None:
            self.view.backdrop = None
            self.view.viewport().update()

        self.set_ground(GROUNDS[ground.style](self, ground))

    # Guides
    def begin_guides(self):
        """Put the guide layer in the scene for a drag."""
        self.guide_item.set_guides(())
        if self.guide_item.scene() is None:
            self.scene.addItem(self.guide_item)

    def show_guides(self, guides, view_scale=1.0):
        """Draw what the dragged card has snapped to, or nothing."""
        if self.guide_item.scene() is None:
            self.begin_guides()
        self.guide_item.set_guides(guides, view_scale)

    def end_guides(self):
        """Take the guide layer out of the scene, so nothing counts it."""
        self.guide_item.set_guides(())
        if self.guide_item.scene() is not None:
            self.guide_item.scene().removeItem(self.guide_item)

    # Motion
    def refresh_motion_settings(self):
        self.motion_level = get_motion_level()
        self.desktop_wants_animation = system_animations_enabled()

    def motion_is_enabled(self):
        return self.motion_level != "Off"

    def reactive_is_allowed(self):
        return self.motion_level != "Off"

    def ground_motion_is_allowed(self):
        """Whether the background may move on its own"""
        return (
            self.motion_level == "Full"
            and self.desktop_wants_animation
            and self.isVisible()
            and self.window().isActiveWindow()
        )

    def ambient_is_allowed(self):
        """Whether the cards may drift on their own"""
        return self.ground_motion_is_allowed()

    def set_ground(self, color):
        """Pick the selection and shadow tones that suit this background colour."""
        self.ground_colour = QColor(color)
        self.gilt = gilt_for_ground(color)
        self.shadow_tone = shadow_for_ground(color)
        for card in self._cards:
            card.set_gilt(self.gilt)
            card.set_shadow_tone(*self.shadow_tone)
        self.guide_item.set_tone(self.gilt)

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
            card.set_shadow_tone(*self.shadow_tone)
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
        ground_moves = self.ground_motion_is_allowed()
        # Held still, the pace is wherever it was going, so nothing resumes mid-ease
        if ground_moves:
            self.ground_pace.advance(dt)
        else:
            self.ground_pace.snap()
        if self.view.swirl is not None:
            self.view.swirl.advance(dt, ground_moves, self.ground_pace.value)

    def settle_motion(self):
        """Put every card flat."""
        self.ambient_gain = 0.0
        self.ground_pace.snap()
        for card in self._cards:
            card.settle_motion()
        if self.view.swirl is not None:
            self.view.swirl.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_motion_settings()
        if self.motion_is_enabled():
            self.motion_clock.subscribe(self._advance_motion)

    def hideEvent(self, event):
        super().hideEvent(event)
        # Switched away from or closed, not minimised: an open panel is abandoned
        if not event.spontaneous():
            self.cancel_panels()
        self.motion_clock.unsubscribe(self._advance_motion)
        self.settle_motion()

    def create_gradient_background(self, hue=None):
        """Aura: a radial gradient through hue's three stops"""
        hue = hue or GROUND_HUES[GROUND_HUE_DEFAULT]
        gradient = aura_gradient(hue, QPointF(0, 0), AURA_RADIUS)
        brush = QBrush(gradient)
        self.scene.setBackgroundBrush(brush)
        self.view.setBackgroundBrush(brush)
        return gradient.stops()[0][1]

    def create_swirl_background(self, hue=None):
        """The moving ground, or Aura in the same hue where no GL context can draw it"""
        hue = hue or GROUND_HUES[GROUND_HUE_DEFAULT]
        field = swirl.field()
        if field is None:
            return self.create_gradient_background(hue)
        if self.view.swirl is None:
            self.view.swirl = swirl.SwirlGround(self.view, field, self)
        self.view.swirl.colours = swirl.colour_values(hue)
        self.view.swirl.request()
        # A solid colour for everything that reads the brush rather than the field
        colour = QColor(hue.swirl[0])
        brush = QBrush(colour)
        self.scene.setBackgroundBrush(brush)
        self.view.setBackgroundBrush(brush)
        return colour

    def _drop_swirl(self):
        if self.view.swirl is None:
            return

        self.view.swirl.detach()
        self.view.swirl.deleteLater()
        self.view.swirl = None
        self.view.viewport().update()

    def create_image_background(self, name, positioning, fill):
        """A copied image: tiled on the scene, or else held still over the viewport on fill"""
        path = backgrounds.background_path(name)
        source = image_ground.load(path, positioning, image_ground.decode_bound()) if path else None
        if source is None or source.isNull():
            log.warning("No background image %r to draw; drawing the gradient", name)
            return self.create_gradient_background()
        # Its transparency shows the fill, in every positioning
        source = image_ground.flatten(source, fill)
        if positioning == "tile":
            brush = QBrush(QPixmap.fromImage(source))
        else:
            self.view.backdrop = image_ground.ImageGround(source, positioning, fill)
            self.view.viewport().update()
            brush = QBrush(QColor(fill))
        self.scene.setBackgroundBrush(brush)
        self.view.setBackgroundBrush(brush)
        return image_ground.average_colour(source)

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
        pattern_brush = QBrush(checkerboard_tile(color, CHECKERBOARD_SQUARE))
        self.view.setBackgroundBrush(pattern_brush)
        return color

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
            "canvas.fit": self.on_home,
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
        if self.background_is_open() or self.arc_is_open():
            self.cancel_panels()
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
        self.paste_action.triggered.connect(lambda _checked=False: self.on_paste_card())
        self.toolbar.addAction(self.paste_action)
        QGuiApplication.clipboard().dataChanged.connect(self.update_paste_action)
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

        if self.SAVES_CANVAS:
            self.save_reading_action = QAction(
                QIcon.fromTheme("document-save"), READINGS["save_reading"], self
            )
            set_tooltip_with_keys(self.save_reading_action, READINGS["save_reading"], "window.save")
            self.save_reading_action.triggered.connect(self.save)
            self.toolbar.addAction(self.save_reading_action)

        # Grey out the arrangement buttons unless you select multiple cards
        self.scene.selectionChanged.connect(self.update_arrange_actions)
        self.scene.selectionChanged.connect(self.edit_state_changed)
        self.update_arrange_actions()

        # View control actions group
        self.view_section = [
            self.toolbar.addSeparator(),
            self.toolbar.addWidget(self.create_section_label(CANVAS["section_view"])),
        ]
        # The group's buttons, without its separator and heading
        self.view_actions = []

        # Zooming is View > Zoom's, whose keys are the window's
        for icon_name, slot, tooltip in (
            ("zoom-in", self.on_zoom_in, CANVAS["zoom_in_tooltip"]),
            ("zoom-out", self.on_zoom_out, CANVAS["zoom_out_tooltip"]),
        ):
            action = QAction(QIcon.fromTheme(icon_name), "", self)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            self.toolbar.addAction(action)
            self.view_actions.append(action)

        fit_action = self.commands["canvas.fit"]
        fit_action.setToolTip(CANVAS["fit_tooltip"])
        self.toolbar.addAction(fit_action)
        self.view_actions.append(fit_action)

        self.fullscreen_action = self.commands["canvas.fullscreen"]
        self.fullscreen_action.setCheckable(True)
        set_tooltip_with_keys(
            self.fullscreen_action, CANVAS["fullscreen_tooltip"], self.fullscreen_action
        )
        self.toolbar.addAction(self.fullscreen_action)
        self.view_actions.append(self.fullscreen_action)
        self.view_section.extend(self.view_actions)

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
            log.warning("Couldn't find main window")
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
        except Exception:
            log.exception("Error accessing card explorer")

        # Use the selected deck or fall back to the default deck
        deck_to_use = selected_deck or self.deck
        if not deck_to_use:
            log.warning("No deck available to draw from!")
            return

        # Get a random card from the selected deck
        card = deck_to_use.random_card()
        if not card:
            log.warning("Could not draw a card from %s!", deck_to_use.metadata.name)
            return

        # Add a 50% chance for the card to be reversed
        is_reversed = random.choice([True, False])

        # Add the card, possibly reversed, using the selected deck
        self.add_specific_card(card, card_deck=deck_to_use, is_reversed=is_reversed, at=at)

        # Log what deck we drew from
        log.debug("Drew card from %s deck", deck_to_use.metadata.name)

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
        return not self.arranging and has_card(mime)

    def paste_card(self, mime, at=None):
        return self.place_card(mime, at)

    def place_card(self, mime, at=None):
        """Resolve a card payload and place every card in it (cascading)

        Returns the first item placed
        """
        resolved = cards_from_mime(mime, deck_library.decks())
        if not resolved:
            log.warning("Nothing placed: the card payload did not resolve")
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

    def on_paste_card(self, at=None):
        mime = QGuiApplication.clipboard().mimeData()
        if self.can_paste_card(mime):
            self.paste_card(mime, at)

    # A real slot for Qt
    @pyqtSlot()
    def update_paste_action(self):
        if self.arranging:
            return
        self.paste_action.setEnabled(self.can_paste_card(QGuiApplication.clipboard().mimeData()))

    def on_card_dropped(self, mime, scene_pos):
        self.place_card(mime, at=scene_pos)

    def make_card_item(self, card, deck, reversed, item_type=DraggableCardItem):
        """An item_type for card, not yet on the canvas, or None if its art won't load."""
        image_path = card.default_image()
        if not image_path or not os.path.exists(image_path):
            log.warning("Card image not found: %s", image_path)
            return None

        # The card is placed at a fitted size; sharper levels load as the view needs them
        art = load_card_art(image_path)
        if art is None:
            log.warning("Failed to load image: %s", image_path)
            return None
        pixmap, source_size = art

        card_item = item_type(pixmap, card, self, deck=deck, reversed=reversed)
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
            log.debug("Added card to canvas: %s (%s)", card.display_name, reversed_status)

            return card_item

        except Exception:
            log.exception("Error adding card to canvas")
            return None

    def add_slot(self, number, position_id, at=None, label="", meaning=""):
        """Add a slot, centred on at or under the pointer"""
        slot = self.SLOT_ITEM(number, position_id, self, label=label, meaning=meaning)
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

    def _toast(self, text):
        toast = getattr(self.window(), "toast", None)
        if toast is not None:
            toast.show_message(text)

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
        """The menu for the card at scene_pos, or None. It selects the card if it wasn't.
        On empty ground, the ground's menu."""
        item = self.card_at(scene_pos)
        if item is None:
            return self.ground_menu(scene_pos)
        if not item.isSelected():
            self.scene.clearSelection()
            item.setSelected(True)
        return self.build_card_menu(item)

    def _menu_entry(self, menu, command_id, slot, enabled=True, words=None, icon=None):
        """An entry with command_id's words, icon and key, which runs slot instead"""
        command = commands.by_id(command_id)
        action = menu.addAction(icon or commands.command_icon(command), "")
        commands.set_menu_text(action, words or command.text, command_id)
        action.setEnabled(enabled)
        action.triggered.connect(lambda _checked=False: slot())
        return action

    def shows_draw_here(self):
        return True

    def ground_menu(self, scene_pos):
        """Paste and draw at scene_pos, select and fit, and Background where the tab keeps one"""
        menu = QMenu(self)
        clipboard = QGuiApplication.clipboard()
        self._menu_entry(
            menu,
            "window.paste_card",
            lambda: self.on_paste_card(at=scene_pos),
            self.can_paste_card(clipboard.mimeData()),
        )
        if self.shows_draw_here():
            self._menu_entry(
                menu,
                "canvas.summon",
                lambda: self.on_draw_card(at=scene_pos),
                not self.arranging,
                words=self.DRAW_HERE,
                icon=self.commands["canvas.summon"].icon(),
            )
        menu.addSeparator()
        self._menu_entry(menu, "window.select_all", self.select_all, self.can_select_all())
        menu.addAction(self.commands["canvas.fit"])
        if self.OWN_GROUND:
            menu.addSeparator()
            command = commands.by_id(BACKGROUND_COMMAND)
            action = menu.addAction(commands.command_icon(command), command.text)
            action.triggered.connect(self.edit_background)
        return menu

    def build_card_menu(self, item):
        menu = QMenu(self)
        open_action = menu.addAction(QIcon.fromTheme("document-open"), CANVAS["open_card"])
        open_action.triggered.connect(lambda: self.open_card_view(item))
        menu.addSeparator()
        self._menu_entry(menu, "window.copy_card", self.copy_card, self.can_copy_card())
        self._menu_entry(menu, "window.cut", self.cut_card, self.can_cut_card())
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
        current = DeckLibrary.path_key(item.deck.root_path) if item.deck else None
        card_id = item.card_data.canonical_id if item.card_data else None
        others = 0
        for deck, card in deck_library.decks_containing(card_id) if card_id else []:
            action = swap_menu.addAction(deck.metadata.name)
            if DeckLibrary.path_key(deck.root_path) == current:
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
        if self.saved_reading is not None:
            self.saved_reading.schedule()
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
        {"in": self.on_zoom_in, "out": self.on_zoom_out, "reset": self.on_home}[how]()

    # Canvas Control Methods
    def on_zoom_in(self):
        """Zoom into the canvas"""
        self._on_camera_taken()
        self.view.zoom_by_from_center(1.2)

    def on_zoom_out(self):
        """Zoom out of the canvas"""
        self._on_camera_taken()
        self.view.zoom_by_from_center(0.8)

    def on_home(self):
        """Take the camera home: every card in view, never closer than 1x"""
        self._on_camera_taken()
        self.view.go_home()

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
        # One panel at a time
        if self.background_is_open():
            self.background_panel.cancel()
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

    def _on_arc_closed(self):
        self.arc_settings = self.arc_popover.settings()
        self._arc_following = False
        self.set_arranging(False)

    # -- the tab's own ground ------------------------------------------------

    def edit_background(self):
        """The Background panel: follow the default, or a ground of the tab's own"""
        if not self.OWN_GROUND:
            return None
        if self.background_is_open():
            self.background_panel.setFocus()
            return self.background_panel
        # One panel at a time
        if self.arc_is_open():
            self.arc_popover.cancel()
        if self.background_panel is not None:
            self.background_panel.deleteLater()
        self.background_panel = panel = BackgroundPanel(self, self.canvas_area)
        panel.applied.connect(self._on_background_applied)
        panel.default_changed.connect(self.default_ground_changed)
        panel.open()
        return panel

    def background_is_open(self):
        return self.background_panel is not None and not self.background_panel.finished

    def _on_background_applied(self):
        if self.saved_reading is not None:
            self.saved_reading.schedule()

    def cancel_panels(self):
        """Put back whatever an open panel changed"""
        if self.background_is_open():
            self.background_panel.cancel()
        if self.arc_is_open():
            self.arc_popover.cancel()

    def _on_camera_taken(self):
        self._arc_following = False

    def _follow_arc(self):
        if self._arc_following:
            popover = self.arc_popover
            self.keep_in_sight(popover.cards_rect(), popover.free_region())

    def keep_in_sight(self, rect, free):
        """Bring scene `rect` into `free`, a part of the viewport, moving the view as little as
        it can. Never a zoom in."""
        rect = rect.adjusted(-HOME_MARGIN, -HOME_MARGIN, HOME_MARGIN, HOME_MARGIN)
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
            marks = snapped(layout_marks(card_marks(self.cards()), MINIMAP.max_fill))
        if marks == self._tab_marks:
            return
        self._tab_marks = marks
        self._tab_icon = spread_icon(marks) if marks else self.empty_tab_icon()
        self.tab_label_changed.emit()

    def elided_title(self, name):
        """name, cut short to fit a tab"""
        metrics = QFontMetrics(self.font())
        width = metrics.averageCharWidth() * TAB_TITLE_CHARS
        return metrics.elidedText(name, Qt.TextElideMode.ElideRight, width)

    def tab_title(self):
        if self.saved_reading is not None:
            return self.elided_title(self.saved_reading.label())
        return self.tab_name

    def tab_tooltip(self):
        if self.saved_reading is None:
            return ""
        name = self.saved_reading.label()
        return name if name != self.tab_title() else ""

    def rename_text(self):
        """What the rename dialog starts from"""
        if self.saved_reading is not None:
            return self.saved_reading.question()
        return self.tab_name

    def rename_dialog_text(self):
        """The rename dialog's title and prompt"""
        return MAIN_WINDOW["rename_canvas"], MAIN_WINDOW["rename_canvas_prompt"]

    def rename(self, name):
        # A reading is named by its Question
        if self.saved_reading is not None:
            self.saved_reading.set_question(name)
            return
        self.tab_name = name
        self.named_by_hand = True
        self.tab_label_changed.emit()

    # -- keeping the canvas as a reading -----------------------------------

    @property
    def reading_path(self):
        """The reading's folder, or None while the canvas is scratch"""
        return self.saved_reading.path if self.saved_reading is not None else None

    def save_label(self):
        return READINGS["save_reading"] if self.SAVES_CANVAS else None

    def can_save(self):
        return self.SAVES_CANVAS and self.saved_reading is None

    def save(self):
        """Keep this canvas as a new reading, done now"""
        if not self.can_save():
            return False
        try:
            path = readings.new_reading_dir()
        except OSError as error:
            log.exception("Could not make a folder for a reading: %s", error)
            return False
        reading = new_reading()

        if self.named_by_hand:
            reading = replace(reading, question=self.tab_name)

        self.save_as(path, reading)
        saved = self.saved_reading.write()
        self.saved_reading.pane.question_edit.setFocus()
        return saved

    def save_as(self, path, reading):
        """From now on, this canvas is the reading in folder path, and writes itself there"""
        pane = SavedCanvasPane(self, Path(path), reading)
        self.saved_reading = SavedReading(self, path, reading, pane)
        self.saved_reading.label_changed.connect(self.tab_label_changed)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout.replaceWidget(self.canvas_area, self.splitter)
        self.splitter.addWidget(self.canvas_area)
        self.saved_reading.pane.dock(self.splitter)
        self.pane_action = self.saved_reading.pane.toggle_action(self, SPREADS["pane_tooltip"])
        self.toolbar.addAction(self.pane_action)

        self.save_reading_action.setEnabled(False)
        self.tab_label_changed.emit()

    def reading_contents(self, base):
        """base, holding this canvas's cards and ground as they are now"""
        deck, cards = cards_of(self.cards(), self.unrestored)
        return replace(base, deck=deck, cards=cards, ground=self.ground)

    def restore_cards(self, reading, decks, reference):
        """Lay reading's cards out exactly as they were saved, each in its deck"""
        resolved = resolve_decks(reading.cards, decks, reference)
        for card in reading.cards:
            self.restore_card(card, resolved[card.deck])

    def restore_card(self, card, deck, item_type=DraggableCardItem):
        """Lay ReadingCard card out in deck exactly as it was saved, and return its item, or None
        if deck has no such card or its art won't load; such a card is kept to be written back"""
        data = self._card_in(deck, card.id)
        if data is None:
            log.warning("Skipped card %r: its deck has no such card", card.id)
            self.unrestored.append(card)
            return None
        item = self.make_card_item(data, deck, card.reversed, item_type=item_type)
        if item is None:
            self.unrestored.append(card)
            return None
        item.kept_card = card
        item.restore(QPointF(card.x, card.y), card.z, card.rotation)
        self.scene.addItem(item)
        self._top_z = max(self._top_z, card.z)
        self._bottom_z = min(self._bottom_z, card.z)
        return item

    @staticmethod
    def _card_in(deck, card_id):
        if deck is None:
            return None
        try:
            return deck.find_card(card_id)
        except Exception:
            return None

    def flush_pending_edits(self):
        if self.saved_reading is not None:
            self.saved_reading.flush()

    def about_to_close(self):
        # Removing the tab hides it, and hiding settles its motion, which can finish a turn: settled
        # now, the turn is in the last write rather than one the closed tab would make later
        self.settle_motion()
        self.flush_pending_edits()
        if self.saved_reading is not None:
            self.saved_reading.close()

    def tab_icon(self):
        return self._tab_icon
