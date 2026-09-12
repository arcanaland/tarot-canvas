import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QStyle,
    QStyleOptionGraphicsItem,
)

from tarot_canvas.ui.canvas.detail import art_loader, detail_level, top_level
from tarot_canvas.ui.canvas.motion import (
    AMBIENT_SCALE_DRAG,
    AMBIENT_SCALE_HOVER,
    HOVER_TILT_DEG,
    LEAN_DEG_PER_PX,
    LEAN_MAX_DEG,
    LEAN_RATE,
    LEAN_REST_PX,
    LIFT_DRAG,
    LIFT_HOVER,
    LIFT_PLACED,
    LIFT_PRESSED,
    LIFT_REST,
    LIFT_SELECTED,
    MOTION_EPSILON_PX,
    ORIENT_RATE,
    REACTIVE_RATE,
    SHADOW_BLUR_PX,
    SHADOW_EPSILON_PX,
    SHADOW_LIFT_EPSILON,
    SHADOW_Z_OFFSET,
    SPIN_RATE,
    AmbientDrift,
    MotionChannels,
    Spring,
    approach,
    build_contact_shadow,
    max_corner_delta,
    rest,
    shadow_geometry,
)
from tarot_canvas.ui.canvas.selection import GILT_ON_DARK, SelectionMarks

# Degrees of Z rotation on hover
HOVER_PUNCH_DEG = 2.0


def _clamp(value, limit):
    return max(-limit, min(limit, value))


class ContactShadowItem(QGraphicsPixmapItem):
    """The blurred silhouette of a card"""

    def __init__(self, pixmap):
        super().__init__(pixmap)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setTransformOriginPoint(self.boundingRect().center())


class DraggableCardItem(QGraphicsPixmapItem):
    """A card on the playground canvas"""

    def __init__(self, pixmap, card_data, parent_tab=None):
        super().__init__(pixmap)
        self.card_data = card_data
        self.parent_tab = parent_tab
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

        self.motion = MotionChannels()
        self._drift = AmbientDrift(card_data.get("id") or card_data.get("name") or "")
        self._applied = None
        self._applied_corners = None
        self._view_scale = 1.0
        self._shadow_pos = None
        self._shadow_lift = None
        self._shadow_angle = None
        self._registered_tab = None

        self.shadow = ContactShadowItem(build_contact_shadow(pixmap))
        self._shadow_pad = float(round(SHADOW_BLUR_PX))
        shadow_rect = self.shadow.boundingRect()
        # How far the shadow's corners sit from the centre it turns about
        self._shadow_reach = max(math.hypot(shadow_rect.width(), shadow_rect.height()) / 2.0, 1.0)
        self.shadow.setZValue(self.zValue() + SHADOW_Z_OFFSET)
        self.marks = SelectionMarks(self)

        # Level of detail
        self._base = pixmap
        self._art_path = None
        self._level = 1
        self._wanted_level = 1
        self._top_level = 1

        self._hovering = False
        self._pressed = False
        self._dragging = False
        self._group_dragging = False
        self._hover_face = (0.0, 0.0)
        self._ambient_scale = 1.0
        self._visual_pos = QPointF(self.pos())
        self._lift = Spring(LIFT_REST)
        self._apply_motion()

    # Motion state
    @property
    def orient(self):
        """The card's logical rotation in degrees."""
        return self.motion.orient

    def set_orient(self, degrees):
        """Turn the card."""
        previous = self.motion.orient + self.motion.orient_lag
        self.motion.orient = float(degrees) % 360

        if self._reactive_allowed():
            self.motion.orient_lag = (previous - self.motion.orient + 180.0) % 360.0 - 180.0
        else:
            self.motion.orient_lag = 0.0

        self._apply_motion()

    def place_and_settle(self):
        """Pop in and spring back"""
        if not self._reactive_allowed():
            return

        self._lift.snap(LIFT_PLACED)
        self.motion.lift = LIFT_PLACED
        self._apply_motion()

    def _reactive_allowed(self):
        tab = self.parent_tab
        if tab is None or not hasattr(tab, "reactive_is_allowed"):
            return False
        return tab.reactive_is_allowed()

    def _lift_target(self):
        if self._group_dragging:
            return LIFT_SELECTED
        if self._dragging:
            return LIFT_DRAG
        if self._pressed:
            return LIFT_PRESSED
        if self._hovering:
            return LIFT_HOVER
        if self.isSelected():
            return LIFT_SELECTED
        return LIFT_REST

    def _ambient_scale_target(self):
        if self._group_dragging:
            return 1.0
        if self._dragging:
            return AMBIENT_SCALE_DRAG
        if self._hovering:
            return AMBIENT_SCALE_HOVER
        return 1.0

    def _face_target(self, dt):
        """banking into a drag or facing the cursor"""
        position = self.pos()
        self._visual_pos = QPointF(
            approach(self._visual_pos.x(), position.x(), LEAN_RATE, dt),
            approach(self._visual_pos.y(), position.y(), LEAN_RATE, dt),
        )

        if (
            abs(position.x() - self._visual_pos.x()) < LEAN_REST_PX
            and abs(position.y() - self._visual_pos.y()) < LEAN_REST_PX
        ):
            self._visual_pos = QPointF(position)
        if self._group_dragging:
            return (0.0, 0.0)
        if self._dragging:
            error = self.pos() - self._visual_pos
            return (
                _clamp(-error.y() * LEAN_DEG_PER_PX, LEAN_MAX_DEG),
                _clamp(-error.x() * LEAN_DEG_PER_PX, LEAN_MAX_DEG),
            )
        if self._hovering:
            return self._hover_face
        return (0.0, 0.0)

    def advance_motion(self, t, dt, ambient_gain, view_scale=1.0):
        """Step one frame"""
        self._view_scale = view_scale
        self._ambient_scale = approach(
            self._ambient_scale, self._ambient_scale_target(), REACTIVE_RATE, dt
        )

        gain = ambient_gain * self._ambient_scale
        tilt_x, tilt_y, drift_x, drift_y = self._drift.sample(t)
        self.motion.tilt_x = tilt_x * gain
        self.motion.tilt_y = tilt_y * gain
        self.motion.drift_x = drift_x * gain
        self.motion.drift_y = drift_y * gain

        face_x, face_y = self._face_target(dt)
        self.motion.face_x = rest(approach(self.motion.face_x, face_x, REACTIVE_RATE, dt), face_x)
        self.motion.face_y = rest(approach(self.motion.face_y, face_y, REACTIVE_RATE, dt), face_y)
        self.motion.spin = rest(approach(self.motion.spin, 0.0, SPIN_RATE, dt), 0.0)
        self.motion.orient_lag = rest(approach(self.motion.orient_lag, 0.0, ORIENT_RATE, dt), 0.0)
        self.motion.lift = self._lift.advance(self._lift_target(), dt)
        applied = self._apply_motion()
        self.marks.advance(dt)
        return applied

    def settle_motion(self):
        """Stop moving fool"""
        self._hovering = False
        self._pressed = False
        self._dragging = False
        self._group_dragging = False
        self._hover_face = (0.0, 0.0)
        self._ambient_scale = 1.0
        self._visual_pos = QPointF(self.pos())
        self._lift.snap(LIFT_REST)
        channels = self.motion
        channels.tilt_x = channels.tilt_y = 0.0
        channels.drift_x = channels.drift_y = 0.0
        channels.face_x = channels.face_y = 0.0
        channels.spin = channels.orient_lag = 0.0
        channels.lift = LIFT_REST
        applied = self._apply_motion()
        self.marks.settle()
        return applied

    def _apply_motion(self):
        """Compose all motion channels into the a single transform"""
        snapshot = self.motion.snapshot()
        if snapshot == self._applied:
            return False
        rect = self.boundingRect()
        transform = self.motion.compose(rect.width(), rect.height())
        corners = tuple(
            transform.map(point) for point in self.motion.corners(rect.width(), rect.height())
        )
        if self._applied_corners is not None and not self.motion.at_rest():
            threshold = MOTION_EPSILON_PX / max(self._view_scale, 1e-6)
            if max_corner_delta(self._applied_corners, corners) < threshold:
                return False
        self.setTransform(transform)
        self._applied = snapshot
        self._applied_corners = corners
        self._place_shadow()
        return True

    def _refresh_view_scale(self):
        """Re-read the zoom from the scene's view."""
        scene = self.scene()
        views = scene.views() if scene is not None else ()
        if views:
            self._view_scale = abs(views[0].transform().m11())

    def view_scale(self):
        return self._view_scale

    def set_view_scale(self, view_scale):
        self._view_scale = view_scale
        self.marks.set_view_scale(view_scale)

    def gilt_tone(self):
        """The selection colour for a ard."""
        tab = self._registered_tab or self.parent_tab
        return getattr(tab, "gilt", None) or GILT_ON_DARK

    def set_gilt(self, color):
        self.marks.set_tone(color)

    def _place_shadow(self):
        lift = self.motion.lift
        offset, scale, opacity = shadow_geometry(lift)
        rect = self.boundingRect()
        shadow_rect = self.shadow.boundingRect()
        x = self.pos().x() + (rect.width() - shadow_rect.width()) / 2.0 + self.motion.drift_x
        y = (
            self.pos().y()
            + (rect.height() - shadow_rect.height()) / 2.0
            + self.motion.drift_y
            + offset
        )
        threshold = SHADOW_EPSILON_PX / max(self._view_scale, 1e-6)
        if (
            self._shadow_pos is None
            or abs(x - self._shadow_pos[0]) >= threshold
            or abs(y - self._shadow_pos[1]) >= threshold
        ):
            self.shadow.setPos(x, y)
            self._shadow_pos = (x, y)
        if self._shadow_lift is None or abs(lift - self._shadow_lift) >= SHADOW_LIFT_EPSILON:
            self.shadow.setScale(scale)
            self.shadow.setOpacity(opacity)
            self._shadow_lift = lift

        # rotate shadow without perspective tilt
        angle = self.motion.orient + self.motion.orient_lag + self.motion.spin
        settled = self.motion.orient_lag == 0.0 and self.motion.spin == 0.0
        angle_threshold = math.degrees(threshold / self._shadow_reach)
        if self._shadow_angle is None or (
            angle != self._shadow_angle
            and (settled or abs(angle - self._shadow_angle) >= angle_threshold)
        ):
            self.shadow.setRotation(angle)
            self._shadow_angle = angle

        self.marks.place_aureole()

    # Level of detail
    def set_art_source(self, path, source_size):
        """Where to load sharper levels of this card's art from."""
        self._art_path = path
        self._top_level = top_level(source_size, self._base.size())

    def detail(self):
        """The level currently shown."""
        return self._level

    def set_detail(self, device_scale):
        """Show the level for device_scale device px per logical px, loading if need be."""
        level = detail_level(device_scale, self._top_level)
        if level == self._wanted_level:
            return
        self._wanted_level = level
        if level == 1:
            self._show_level(1, self._base)
        elif level < self._level:
            size = self._base.size() * level
            self._show_level(
                level,
                self.pixmap().scaled(
                    size,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ),
            )
        else:
            art_loader().request(self, self._art_path, self._base.size() * level, level)

    def receive_detail(self, level, image):
        """A level the loader decoded, arriving potentially after the zoom."""
        if level == self._wanted_level:
            self._show_level(level, QPixmap.fromImage(image))

    def _show_level(self, level, pixmap):
        pixmap.setDevicePixelRatio(level)
        self.setPixmap(pixmap)
        self._level = level

    # Qt plumbing
    def shape(self):
        """The card's rectangle."""
        path = QPainterPath()
        path.addRect(QRectF(self.offset(), self.pixmap().deviceIndependentSize()))
        return path

    def paint(self, painter, option, widget=None):
        """Main paint for the card"""
        if option.state & QStyle.StateFlag.State_Selected:
            option = QStyleOptionGraphicsItem(option)
            option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)

    def itemChange(self, change, value):
        """Keep the shadow and the aureole with their card"""
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            if value is not None:
                value.addItem(self.shadow)
                self.marks.join_scene(value)
            else:
                if self.shadow.scene() is not None:
                    self.shadow.scene().removeItem(self.shadow)
                self.marks.leave_scene()
            self._register_with_scene(value)
        elif change == QGraphicsItem.GraphicsItemChange.ItemZValueHasChanged:
            self.shadow.setZValue(self.zValue() + SHADOW_Z_OFFSET)
            self.marks.restack(self.zValue())
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._refresh_view_scale()
            self._place_shadow()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            selected = self.isSelected()
            if selected:
                self._refresh_view_scale()
            self.marks.set_selected(selected, animate=self._reactive_allowed())
        return super().itemChange(change, value)

    def _register_with_scene(self, scene):
        """Join or leave the card list"""
        if self._registered_tab is not None:
            self._registered_tab.unregister_card(self)
            self._registered_tab = None

        owner = scene.parent() if scene is not None else None

        if owner is not None and hasattr(owner, "register_card"):
            owner.register_card(self)
            self._registered_tab = owner

    def begin_hover(self, point):
        first = not self._hovering
        self._hovering = True
        if first and self._reactive_allowed():
            self.motion.spin = HOVER_PUNCH_DEG * (1.0 if self._drift.sample(0.0)[0] >= 0 else -1.0)
        self._hover_face = self._face_toward(point)

    def end_hover(self):
        self._hovering = False
        self._hover_face = (0.0, 0.0)

    def hoverEnterEvent(self, event):
        self.begin_hover(event.pos())
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        self.begin_hover(event.pos())
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.end_hover()
        super().hoverLeaveEvent(event)

    def _face_toward(self, point):
        """Tilt so the side under the cursor dips away as though the card were pressed."""
        rect = self.boundingRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return (0.0, 0.0)
        dx = (point.x() - rect.width() / 2.0) / (rect.width() / 2.0)
        dy = (point.y() - rect.height() / 2.0) / (rect.height() / 2.0)
        return (
            _clamp(dy, 1.0) * -HOVER_TILT_DEG,
            _clamp(dx, 1.0) * -HOVER_TILT_DEG,
        )

    def mousePressEvent(self, event):
        self._pressed = True
        self._visual_pos = QPointF(self.pos())
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (self._dragging or self._group_dragging):
            self.begin_drag()
        super().mouseMoveEvent(event)

    def begin_drag(self):
        moving = self._moving_cards()
        if len(moving) > 1:
            self._group_dragging = True
        else:
            self._dragging = True
        tab = self._registered_tab
        if tab is not None and hasattr(tab, "raise_cards"):
            tab.raise_cards(moving)

    def _moving_cards(self):
        """The cards a drag of this one moves: the whole selection if this card is in it."""
        scene = self.scene()
        if scene is None or not self.isSelected():
            return [self]
        return [item for item in scene.selectedItems() if isinstance(item, DraggableCardItem)]

    def end_drag(self):
        self._pressed = False
        self._dragging = False
        self._group_dragging = False

    def mouseReleaseEvent(self, event):
        self.end_drag()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double click events to open a card view tab"""
        if self.parent_tab and hasattr(self.parent_tab, "open_card_view"):
            self.parent_tab.open_card_view(self.card_data)
        super().mouseDoubleClickEvent(event)
