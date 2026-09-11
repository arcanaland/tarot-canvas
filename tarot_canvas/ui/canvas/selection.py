"""Selection as light: an aureole around a selected card and gilt marks at its corners."""

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsPixmapItem

from tarot_canvas.ui.canvas.motion import REACTIVE_RATE, SHADOW_EPSILON_PX, approach

# The aureole is the shadow's blurred silhouette, filled with gilt instead of black
AUREOLE_OPACITY = 0.35
AUREOLE_Z_OFFSET = -0.75  # beneath the shadow, so the shadow still grounds the card

GILT_ON_DARK = "#FFD99A"  # pale candle-gold
GILT_ON_LIGHT = "#A8741E"  # deep old-gold
LIGHT_GROUND_LUMINANCE = 0.5

# Corner geometry, as fractions of the card's short side unless noted
CORNER_ARM = 0.12
CORNER_ARM_CAP = 0.35  # opposite arms never meet
CORNER_GAP = 0.025  # outside the card's edge
CORNER_ROOT = 3.0  # item px at the join, tapering to nothing at the tip
CORNER_MIN_ROOT_SCREEN_PX = 2.0
CORNER_MIN_ARM_SCREEN_PX = 8.0
CORNER_REBUILD_RATIO = 1.1  # rebuild when the floor moves the geometry by more than this

# Corner glint
CORNER_BASE_OPACITY = 0.7
CORNER_GLINT_GAIN = 0.05  # per degree a corner has turned down
CORNER_MIN_OPACITY = 0.4
CORNER_GATHER_FROM = 1.08  # scale about the card centre when the corners start to gather in
CORNER_OPACITY_EPSILON = 0.01

SELECTION_RATE = REACTIVE_RATE
SELECTION_REST_EPSILON = 1e-3

# Outward direction of each corner, in the order MotionChannels.corners() gives them
CORNERS = ((-1, -1), (1, -1), (1, 1), (-1, 1))

# Cubic control-point distance for a quarter circle of unit radius
_KAPPA = 0.5522847498


def ground_luminance(color):
    """Approximate lightness of a background colour in [0, 1]."""
    color = QColor(color)
    return 0.2126 * color.redF() + 0.7152 * color.greenF() + 0.0722 * color.blueF()


def gilt_for_ground(color):
    """Light on a dark ground, gilt ink on a light one: one hue, two luminances."""
    if ground_luminance(color) > LIGHT_GROUND_LUMINANCE:
        return QColor(GILT_ON_LIGHT)
    return QColor(GILT_ON_DARK)


def tint_silhouette(pixmap, color):
    """The pixmap's alpha, filled with a single colour."""
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(image.rect(), QColor(color))
    painter.end()
    return QPixmap.fromImage(image)


def corner_geometry(width, height, view_scale):
    """(arm, root, gap) in item px, with the arm and root held to a screen-space floor."""
    short = min(width, height)
    zoom = max(view_scale, 1e-6)
    gap = CORNER_GAP * short
    root = max(CORNER_ROOT, CORNER_MIN_ROOT_SCREEN_PX / zoom)
    arm = max(CORNER_ARM * short, CORNER_MIN_ARM_SCREEN_PX / zoom)
    arm = min(arm, CORNER_ARM_CAP * short)
    return arm, root, gap


def geometry_moved(before, after):
    """Whether any of two corner geometries differ by more than CORNER_REBUILD_RATIO."""
    for old, new in zip(before, after, strict=True):
        low, high = sorted((old, new))
        if low <= 0.0 or high / low > CORNER_REBUILD_RATIO:
            return True
    return False


def corner_path(width, height, outward, arm, root, gap):
    """One tapered L: two arms along the card's edges, joined by a rounded outer corner.

    Built in "outward" coordinates (a, b) measured away from the card corner along each
    edge, then mirrored into item coordinates, so every corner is the same shape.
    """
    sx, sy = outward
    corner_x = width if sx > 0 else 0.0
    corner_y = height if sy > 0 else 0.0

    def point(a, b):
        return QPointF(corner_x + sx * a, corner_y + sy * b)

    r = root / 2.0
    c = gap + r  # the centreline, set far enough out that the stroke never touches the art
    tip = c - max(arm, gap + 2.0 * root)  # measured from the corner, so negative is inward
    k = _KAPPA * r

    path = QPainterPath(point(tip, c))
    path.lineTo(point(c, c + r))
    path.cubicTo(point(c + k, c + r), point(c + r, c + k), point(c + r, c))
    path.lineTo(point(c, tip))
    path.lineTo(point(gap, gap))
    path.closeSubpath()
    return path


def corner_dips(tilt_x, tilt_y, spin):
    """Degrees each corner has turned down, away from the viewer, in item corner order.

    compose() applies the tilt after the spin, so it is screen-aligned: tilt_y > 0 sends
    the screen-left edge down and tilt_x > 0 the screen-top. A corner's dip is its screen
    direction against that tilt. The drag-tilt report's one rule (the side the gesture
    points at goes down) then makes the corners under a hover, or leading a drag, glint.
    """
    radians = math.radians(spin)
    cos, sin = math.cos(radians), math.sin(radians)
    dips = []
    for sx, sy in CORNERS:
        x = sx * cos - sy * sin
        y = sx * sin + sy * cos
        dips.append(-(x * tilt_y + y * tilt_x) / 2.0)
    return tuple(dips)


def corner_glint(dip):
    """Opacity of a corner that has turned dip degrees down."""
    return max(CORNER_MIN_OPACITY, min(1.0, CORNER_BASE_OPACITY + CORNER_GLINT_GAIN * dip))


class AureoleItem(QGraphicsPixmapItem):
    """The warm glow around a selected card"""

    def __init__(self, pixmap):
        super().__init__(pixmap)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setTransformOriginPoint(self.boundingRect().center())
        self.setVisible(False)


class GiltCornerItem(QGraphicsPathItem):
    """One corner mark, a child of its card so it rides the card's tilt"""

    def __init__(self, parent, color):
        super().__init__(parent)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(color))
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setVisible(False)


class SelectionMarks:
    """The aureole and the four gilt corners of one card, built on its first selection."""

    def __init__(self, card):
        self._card = card
        self._tone = None
        self.aureole = None
        self.corners = ()
        self.level = 0.0  # 0 is unselected, 1 is fully lit
        self._target = 0.0
        self._geometry = None
        self._opacities = None
        self._gather = None
        self._aureole_place = None

    @property
    def built(self):
        return self.aureole is not None

    # Card lifecycle
    def join_scene(self, scene):
        if self.aureole is not None and scene is not None:
            scene.addItem(self.aureole)

    def leave_scene(self):
        if self.aureole is not None and self.aureole.scene() is not None:
            self.aureole.scene().removeItem(self.aureole)

    def restack(self, z):
        if self.aureole is not None:
            self.aureole.setZValue(z + AUREOLE_Z_OFFSET)

    # State
    def set_selected(self, selected, animate):
        self._target = 1.0 if selected else 0.0
        if selected and not self.built:
            self._build()
        if not animate:
            self.level = self._target
        self._aureole_place = None
        self.apply()

    def advance(self, dt):
        if self.level != self._target:
            self.level = approach(self.level, self._target, SELECTION_RATE, dt)
            if abs(self.level - self._target) < SELECTION_REST_EPSILON:
                self.level = self._target
        self.apply()

    def settle(self):
        self.level = self._target
        self.apply()

    def set_tone(self, color):
        color = QColor(color)
        if self._tone == color:
            return
        self._tone = color
        if not self.built:
            return
        self.aureole.setPixmap(tint_silhouette(self._card.shadow.pixmap(), color))
        for corner in self.corners:
            corner.setBrush(QBrush(color))

    def set_view_scale(self, view_scale):
        """Rebuild the corners when the zoom floor has moved them noticeably."""
        if not self.built:
            return
        rect = self._card.boundingRect()
        geometry = corner_geometry(rect.width(), rect.height(), view_scale)
        if geometry_moved(self._geometry, geometry):
            self._shape_corners(geometry)

    # Building
    def _build(self):
        card = self._card
        if self._tone is None:
            self._tone = QColor(card.gilt_tone())
        self.aureole = AureoleItem(tint_silhouette(card.shadow.pixmap(), self._tone))
        self.restack(card.zValue())
        self.join_scene(card.scene())

        rect = card.boundingRect()
        self.corners = tuple(GiltCornerItem(card, self._tone) for _ in CORNERS)
        for corner in self.corners:
            corner.setTransformOriginPoint(rect.center())
        self._shape_corners(corner_geometry(rect.width(), rect.height(), card.view_scale()))

    def _shape_corners(self, geometry):
        rect = self._card.boundingRect()
        arm, root, gap = geometry
        for corner, outward in zip(self.corners, CORNERS, strict=True):
            corner.setPath(corner_path(rect.width(), rect.height(), outward, arm, root, gap))
        self._geometry = geometry

    # Applying
    def apply(self):
        if not self.built:
            return
        visible = self.level > 0.0
        self.aureole.setVisible(visible)
        for corner in self.corners:
            corner.setVisible(visible)
        if not visible:
            self._opacities = None
            return

        self.aureole.setOpacity(AUREOLE_OPACITY * self.level)
        self.place_aureole()

        gather = 1.0 + (CORNER_GATHER_FROM - 1.0) * (1.0 - self.level)
        if gather != self._gather:
            for corner in self.corners:
                corner.setScale(gather)
            self._gather = gather

        motion = self._card.motion
        dips = corner_dips(
            motion.tilt_x + motion.face_x,
            motion.tilt_y + motion.face_y,
            motion.orient + motion.orient_lag + motion.spin,
        )
        if self._opacities is None:
            self._opacities = [None] * len(self.corners)
        settled = self.level == self._target and motion.at_rest()
        for i, (corner, dip) in enumerate(zip(self.corners, dips, strict=True)):
            opacity = corner_glint(dip) * self.level
            previous = self._opacities[i]
            if previous is None or abs(opacity - previous) >= CORNER_OPACITY_EPSILON or settled:
                corner.setOpacity(opacity)
                self._opacities[i] = opacity

    def place_aureole(self):
        """Follow position, drift and orient; no lift offset, since light doesn't drop."""
        if self.aureole is None or not self.aureole.isVisible():
            return
        card = self._card
        motion = card.motion
        rect = card.boundingRect()
        aureole_rect = self.aureole.boundingRect()
        x = card.pos().x() + (rect.width() - aureole_rect.width()) / 2.0 + motion.drift_x
        y = card.pos().y() + (rect.height() - aureole_rect.height()) / 2.0 + motion.drift_y
        angle = motion.orient + motion.orient_lag + motion.spin
        place = (x, y, angle, motion.lift)

        previous = self._aureole_place
        if previous is not None and not motion.at_rest():
            threshold = SHADOW_EPSILON_PX / max(card.view_scale(), 1e-6)
            if (
                abs(x - previous[0]) < threshold
                and abs(y - previous[1]) < threshold
                and abs(angle - previous[2]) < math.degrees(threshold / self._reach())
                and abs(motion.lift - previous[3]) < 1e-3
            ):
                return
        self.aureole.setPos(x, y)
        self.aureole.setRotation(angle)
        self.aureole.setScale(motion.lift)
        self._aureole_place = place

    def _reach(self):
        """How far the aureole's corners sit from the centre it turns about."""
        rect = self.aureole.boundingRect()
        return max(math.hypot(rect.width(), rect.height()) / 2.0, 1.0)
