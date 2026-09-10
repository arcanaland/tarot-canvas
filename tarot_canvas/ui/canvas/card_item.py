from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem

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
    SPIN_RATE,
    AmbientDrift,
    MotionChannels,
    Spring,
    approach,
    max_corner_delta,
    rest,
)

# Degrees of Z rotation on hover
HOVER_PUNCH_DEG = 2.0


def _clamp(value, limit):
    return max(-limit, min(limit, value))


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
        self._registered_tab = None

        self._hovering = False
        self._pressed = False
        self._dragging = False
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
        return self._apply_motion()

    def settle_motion(self):
        """Stop moving fool"""
        self._hovering = False
        self._pressed = False
        self._dragging = False
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
        return self._apply_motion()

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
        return True

    # Qt plumbing
    def itemChange(self, change, value):
        """Keep the tab's card list in step with the scene the card is in."""
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            self._register_with_scene(value)
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
        self._dragging = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double click events to open a card view tab"""
        if self.parent_tab and hasattr(self.parent_tab, "open_card_view"):
            self.parent_tab.open_card_view(self.card_data)
        super().mouseDoubleClickEvent(event)
