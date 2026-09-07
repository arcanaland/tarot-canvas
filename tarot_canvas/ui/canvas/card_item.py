from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsPixmapItem

from tarot_canvas.ui.canvas.motion import AmbientDrift, MotionChannels, approach

# How fast a reactive channel chases its target, in e-folds per second.
REACTIVE_RATE = 12.0


class DraggableCardItem(QGraphicsPixmapItem):
    """A card on the playground canvas: draggable, selectable, opens a card view.

    The card's transform is owned entirely by `self.motion`: nothing here calls
    `setRotation`, `setScale` or `setTransformOriginPoint`. Callers that want the card
    turned — the reversed-180 state, the rotate-90 command — write the `orient` channel
    and let `_apply_motion` compose it.
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
        self._apply_motion()

    @property
    def orient(self):
        """The card's logical rotation in degrees — what `rotation()` used to hold."""
        return self.motion.orient

    def set_orient(self, degrees):
        """Turn the card. Card state, not motion: no gate suppresses it."""
        self.motion.orient = float(degrees) % 360
        self._apply_motion()

    def _apply_motion(self):
        """Compose the channels into the item's transform, if any of them moved."""
        snapshot = self.motion.snapshot()
        if snapshot == self._applied:
            return False
        rect = self.boundingRect()
        self.setTransform(self.motion.compose(rect.width(), rect.height()))
        self._applied = snapshot
        return True

    def advance_motion(self, t, dt, ambient_gain):
        """Advance one frame. Returns whether the card's transform actually changed.

        Ambient channels (tilt, drift) are scaled by `ambient_gain` and reactive ones are
        not, which is what makes the reduced-motion tiers a single gate rather than a
        per-effect audit. At a gain of exactly zero the ambient channels land on exactly
        zero, so `_apply_motion` finds an unchanged snapshot and a gated canvas costs no
        repaints at all.
        """
        tilt_x, tilt_y, drift_x, drift_y = self._drift.sample(t)
        self.motion.tilt_x = tilt_x * ambient_gain
        self.motion.tilt_y = tilt_y * ambient_gain
        self.motion.drift_x = drift_x * ambient_gain
        self.motion.drift_y = drift_y * ambient_gain
        self.motion.lift = approach(self.motion.lift, 1.0, REACTIVE_RATE, dt)
        return self._apply_motion()

    def settle_ambient(self):
        """Drop the ambient channels to rest, leaving only card state and reactive ones."""
        self.motion.tilt_x = 0.0
        self.motion.tilt_y = 0.0
        self.motion.drift_x = 0.0
        self.motion.drift_y = 0.0
        return self._apply_motion()

    def mousePressEvent(self, event):
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double click events to open a card view tab"""
        if self.parent_tab and hasattr(self.parent_tab, "open_card_view"):
            self.parent_tab.open_card_view(self.card_data)
        super().mouseDoubleClickEvent(event)
