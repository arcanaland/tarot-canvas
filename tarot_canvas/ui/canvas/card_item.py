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

# Degrees of Z rotation on hover
HOVER_PUNCH_DEG = 2.0


def _clamp(value, limit):
    return max(-limit, min(limit, value))


class ContactShadowItem(QGraphicsPixmapItem):
    """The blurred silhouette that grounds one card.

    A separate scene item rather than a child of the card, for two reasons. A child would
    inherit the card's transform, and a contact shadow does not tilt with the card — it
    lies on the felt while the card turns above it. And a child is clipped into the card's
    own coordinate system, where the penumbra has nowhere to spread.
    """

    def __init__(self, pixmap):
        super().__init__(pixmap)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        # The shadow scales about its own centre and the pixmap never changes, so this is
        # a constant. It used to be recomputed on every placement, which meant a QRectF
        # and a QPointF allocated per card per frame to set the same value back.
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
        self._registered_tab = None

        self.shadow = ContactShadowItem(build_contact_shadow(pixmap))
        self._shadow_pad = float(round(SHADOW_BLUR_PX))
        self.shadow.setZValue(self.zValue() + SHADOW_Z_OFFSET)

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
        self._place_shadow()
        return True

    def _refresh_view_scale(self):
        """Re-read the zoom from the scene's view, for the paths the tick does not drive."""
        scene = self.scene()
        views = scene.views() if scene is not None else ()
        if views:
            self._view_scale = abs(views[0].transform().m11())

    def _place_shadow(self):
        """Put the shadow under the card for the current lift.

        The shadow stays flat — it never takes the card's tilt — and follows the visual
        drift, so a breathing card drags its own shadow with it rather than sliding across
        a pinned one.

        It gets its own, coarser dead-band on top of the card's. The shadow is the largest
        pixmap on the canvas and it draws through an opacity composite, so it is the most
        expensive thing here to move — and being a blur with no edge, it is the least able
        to show that it moved. Its scale and opacity depend only on `lift`, which is pinned
        to exactly LIFT_REST whenever no gesture is in flight, so an ambient-only canvas
        re-scales nothing at all and only ever nudges the position.
        """
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

    # Qt plumbing
    def itemChange(self, change, value):
        """Keep the shadow with its card, so no call site has to remember it exists."""
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            if value is not None:
                value.addItem(self.shadow)
            elif self.shadow.scene() is not None:
                self.shadow.scene().removeItem(self.shadow)
            # The tab's tick iterates its own list of cards rather than filtering
            # `scene.items()` — which builds and z-sorts a Python list of every item,
            # shadows included, sixty times a second. Registering from here rather than
            # from the call sites is the same reasoning as the shadow above: `addItem`
            # and `removeItem` are called from half a dozen places and none of them
            # should have to remember.
            self._register_with_scene(value)
        elif change == QGraphicsItem.GraphicsItemChange.ItemZValueHasChanged:
            # Tracked through itemChange rather than by overriding setZValue, so it holds
            # however the card is restacked — including from Qt's own side.
            self.shadow.setZValue(self.zValue() + SHADOW_Z_OFFSET)
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Also done on the tick, but the clock does not run at motion level Off, and a
            # card dragged then must not leave its shadow behind. The tick is also what
            # normally keeps `_view_scale` fresh, so re-read it here rather than let the
            # shadow's dead-band be sized for the wrong zoom. Only the dragged card gets
            # this, so it is nowhere near the hot path.
            self._refresh_view_scale()
            self._place_shadow()
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
