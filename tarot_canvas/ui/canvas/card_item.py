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
    ORIENT_RATE,
    REACTIVE_RATE,
    SHADOW_BLUR_PX,
    SHADOW_Z_OFFSET,
    SPIN_RATE,
    AmbientDrift,
    MotionChannels,
    Spring,
    approach,
    build_contact_shadow,
    rest,
    shadow_geometry,
)

# Degrees of Z rotation kicked into `spin` when the pointer first arrives over a card. It
# decays straight back to zero, so this is an impulse rather than a state: the punch is the
# card acknowledging the cursor, not a pose it holds.
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


class DraggableCardItem(QGraphicsPixmapItem):
    """A card on the playground canvas: draggable, selectable, opens a card view.

    The card's transform is owned entirely by `self.motion`: nothing here calls
    `setRotation`, `setScale` or `setTransformOriginPoint`. Callers that want the card
    turned — the reversed-180 state, the rotate-90 command — write the `orient` channel
    and let `_apply_motion` compose it.

    Input handlers here never touch a transform either. They write *targets*, and the
    single clock walks every card once a frame to chase them. That is what keeps a hover
    and a drag and the ambient drift from fighting over the same scalar, which is the bug
    the previous wobble implementation could not get out from under.
    """

    def __init__(self, pixmap, card_data, parent_tab=None):
        super().__init__(pixmap)
        self.card_data = card_data
        self.parent_tab = parent_tab
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsPixmapItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        # QGraphicsPixmapItem defaults to FastTransformation, and its paint() sets the
        # SmoothPixmapTransform render hint from this mode — overwriting whatever the
        # view asked for. A rotated card is resampled nearest-neighbour without this,
        # which reads as horizontal shear bands crawling across the face.
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

        self.motion = MotionChannels()
        # Seeded from the card rather than the object, so the Hermit breathes the same way
        # every time it is drawn. Falls back to the name, then to nothing, rather than
        # failing on a card_data that has no id.
        self._drift = AmbientDrift(card_data.get("id") or card_data.get("name") or "")
        self._applied = None

        self.shadow = ContactShadowItem(build_contact_shadow(pixmap))
        self._shadow_pad = float(round(SHADOW_BLUR_PX))
        self.shadow.setZValue(self.zValue() + SHADOW_Z_OFFSET)

        self._hovering = False
        self._pressed = False
        self._dragging = False
        self._hover_face = (0.0, 0.0)
        self._ambient_scale = 1.0
        # The logical position the visual is chasing. The gap between them is never used to
        # displace the card — that would read as input lag on a direct-manipulation drag —
        # only to derive the bank angle, which is RFC-024's "one subtraction".
        self._visual_pos = QPointF(self.pos())
        self._lift = Spring(LIFT_REST)
        self._apply_motion()

    # Motion state
    @property
    def orient(self):
        """The card's logical rotation in degrees — what `rotation()` used to hold."""
        return self.motion.orient

    def set_orient(self, degrees):
        """Turn the card. Card state, not motion: no gate suppresses it.

        The logical angle lands immediately, so `on_flip_card` still branches on an exact
        value; what animates is `orient_lag`, the difference the display has yet to catch
        up on, taken the short way round so a flip does not unwind through 359 degrees.
        """
        previous = self.motion.orient + self.motion.orient_lag
        self.motion.orient = float(degrees) % 360
        if self._reactive_allowed():
            self.motion.orient_lag = (previous - self.motion.orient + 180.0) % 360.0 - 180.0
        else:
            self.motion.orient_lag = 0.0
        self._apply_motion()

    def place_and_settle(self):
        """Arrive large and spring back. Called once, when the card is drawn onto the tab."""
        if not self._reactive_allowed():
            return
        self._lift.snap(LIFT_PLACED)
        self.motion.lift = LIFT_PLACED
        self._apply_motion()

    def _reactive_allowed(self):
        """Whether the reactive tier may play.

        Asked of the tab rather than cached, so there is no per-card flag to keep in step
        with the preferences dialog. Reactive ignores the desktop's reduced-motion hint and
        the window's focus on purpose: RFC-024's ladder keeps this tier under reduced
        motion, and an unfocused window has no cursor over a card to respond to. A card
        with no tab — every unit test that does not supply one — is simply inert.
        """
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
        # Selection gets a resting lift rather than a drawn outline. Qt's own dashed
        # rectangle clashes with the artwork and does not follow the card's perspective,
        # and the corner brackets that would replace it cannot be painted from Python
        # without crashing the suite (TASK-028). Height reads as selected on its own.
        if self.isSelected():
            return LIFT_SELECTED
        return LIFT_REST

    def _ambient_scale_target(self):
        """Ambient yields to intent, in one number."""
        if self._dragging:
            return AMBIENT_SCALE_DRAG
        if self._hovering:
            return AMBIENT_SCALE_HOVER
        return 1.0

    def _face_target(self, dt):
        """Where the reactive tilt is heading: banking into a drag, or facing the cursor.

        The two are states of the same card and cannot both apply, so they compete for one
        channel rather than summing into two.
        """
        position = self.pos()
        self._visual_pos = QPointF(
            approach(self._visual_pos.x(), position.x(), LEAN_RATE, dt),
            approach(self._visual_pos.y(), position.y(), LEAN_RATE, dt),
        )
        # The same floor the reactive channels get, for the same reason: approach() closes
        # the gap asymptotically, and a lean target of a ten-billionth of a degree still
        # keeps every card on the canvas repainting for a drag that ended long ago.
        if (
            abs(position.x() - self._visual_pos.x()) < LEAN_REST_PX
            and abs(position.y() - self._visual_pos.y()) < LEAN_REST_PX
        ):
            self._visual_pos = QPointF(position)
        if self._dragging:
            error = self.pos() - self._visual_pos
            # The card ploughs: the leading edge digs into the felt and the trailing edge
            # lifts. See _face_toward for why both axes are the *negative* of the
            # displacement, and REPORTS/2026-09-07-drag-tilt-direction for why ploughing
            # rather than banking is the right reading for a top-down spread.
            return (
                _clamp(-error.y() * LEAN_DEG_PER_PX, LEAN_MAX_DEG),
                _clamp(-error.x() * LEAN_DEG_PER_PX, LEAN_MAX_DEG),
            )
        if self._hovering:
            return self._hover_face
        return (0.0, 0.0)

    def advance_motion(self, t, dt, ambient_gain):
        """Advance one frame. Returns whether the card's transform actually changed.

        Ambient channels (tilt, drift) are scaled by `ambient_gain` and reactive ones are
        not, which is what makes the reduced-motion tiers a single gate rather than a
        per-effect audit. At a gain of exactly zero the ambient channels land on exactly
        zero, so `_apply_motion` finds an unchanged snapshot and a gated canvas costs no
        repaints at all.
        """
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
        """Bring every channel but the card's own orientation to rest, at once.

        Called when the clock stops. Both tiers are dropped, not just the ambient one: a
        hidden tab freezes whatever gesture was in flight, and a card that comes back
        half-lifted and still banking from a drag that ended two minutes ago is worse than
        one that comes back flat. The hover and press flags go with them, since the pointer
        is demonstrably somewhere else by the time this runs.
        """
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
        """Compose the channels into the item's transform, if any of them moved."""
        snapshot = self.motion.snapshot()
        if snapshot == self._applied:
            return False
        rect = self.boundingRect()
        self.setTransform(self.motion.compose(rect.width(), rect.height()))
        self._applied = snapshot
        self._place_shadow()
        return True

    def _place_shadow(self):
        """Put the shadow under the card for the current lift.

        The shadow stays flat — it never takes the card's tilt — and follows the visual
        drift, so a breathing card drags its own shadow with it rather than sliding across
        a pinned one.
        """
        offset, scale, opacity = shadow_geometry(self.motion.lift)
        rect = self.boundingRect()
        centre_x = self.pos().x() + rect.width() / 2.0 + self.motion.drift_x
        centre_y = self.pos().y() + rect.height() / 2.0 + self.motion.drift_y + offset
        shadow_rect = self.shadow.boundingRect()
        self.shadow.setPos(
            centre_x - shadow_rect.width() / 2.0,
            centre_y - shadow_rect.height() / 2.0,
        )
        self.shadow.setTransformOriginPoint(shadow_rect.center())
        self.shadow.setScale(scale)
        self.shadow.setOpacity(opacity)

    # Qt plumbing
    def itemChange(self, change, value):
        """Keep the shadow with its card, so no call site has to remember it exists."""
        if change == QGraphicsItem.GraphicsItemChange.ItemSceneHasChanged:
            if value is not None:
                value.addItem(self.shadow)
            elif self.shadow.scene() is not None:
                self.shadow.scene().removeItem(self.shadow)
        elif change == QGraphicsItem.GraphicsItemChange.ItemZValueHasChanged:
            # Tracked through itemChange rather than by overriding setZValue, so it holds
            # however the card is restacked — including from Qt's own side.
            self.shadow.setZValue(self.zValue() + SHADOW_Z_OFFSET)
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Also done on the tick, but the clock does not run at motion level Off, and a
            # card dragged then must not leave its shadow behind.
            self._place_shadow()
        return super().itemChange(change, value)

    def begin_hover(self, point):
        """The pointer arrived over the card at `point`, in item coordinates.

        Split out from the event handler because a QGraphicsSceneHoverEvent cannot be
        constructed from Python, so this is the only seam a test can reach.
        """
        first = not self._hovering
        self._hovering = True
        if first and self._reactive_allowed():
            # A signed impulse from the card's own drift phase, so a row of cards does not
            # all flick the same way when the pointer runs along it. It decays straight
            # back to zero: the punch is an acknowledgement, not a pose the card holds.
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
        """Tilt so the side under the cursor dips away, as though the card were pressed.

        **One rule, both axes: the tilt is the negative of the displacement.** Whether the
        displacement is the cursor's offset from the card's centre (here) or the card's lag
        behind the pointer (a drag), the side it points at is the side that goes down.
        Deriving the four signs independently is what produced a card that dipped when
        dragged downward and rose when dragged rightward.

        Measured against this `compose()`: `tilt_y > 0` recedes the left edge and
        `tilt_x > 0` recedes the top, so both terms come out negative.
        """
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
