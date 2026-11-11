"""A Ground turned into paint, shared by the canvas and anything that shows a ground small"""

import logging
import math

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPixmap, QRadialGradient

from tarot_canvas.ui.canvas import image_ground, swirl
from tarot_canvas.ui.canvas.ground import checkerboard_partner, ground_hue

log = logging.getLogger(__name__)

# Aura's radius on the canvas, in scene units about the scene origin
AURA_RADIUS = 800

# About this many checkerboard squares span a painted rect
CHECKERBOARD_SQUARES_ACROSS = 6

# Positionings whose scale means nothing in a miniature, painted as crop there
_MINIATURE_AS_CROP = ("tile", "center")

# (hue id, device w, device h) -> the swirl's still frame
_swirl_stills = {}


def aura_gradient(hue, centre, radius):
    """Aura: a radial gradient through hue's three stops"""
    gradient = QRadialGradient(QPointF(centre), radius)
    gradient.setStops(hue.aura_stops())
    return gradient


def checkerboard_tile(color, square):
    """Two squares of color and two of its partner, square px on a side, to tile as a brush"""
    color = QColor(color)
    partner = checkerboard_partner(color)
    pixmap = QPixmap(square * 2, square * 2)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setPen(Qt.PenStyle.NoPen)

    painter.setBrush(QBrush(color))
    painter.drawRect(0, 0, square, square)
    painter.drawRect(square, square, square, square)

    painter.setBrush(QBrush(partner))
    painter.drawRect(0, square, square, square)
    painter.drawRect(square, 0, square, square)

    painter.end()
    return pixmap


def swirl_still(ground, size, ratio):
    """The swirl at rest as an image for size logical px, or None where GL cannot draw it"""
    field = swirl.field()
    if field is None:
        return None
    target = swirl.field_size(size, ratio, swirl.PARAMS["pixel"])
    key = (ground.hue, target.width(), target.height())
    if key in _swirl_stills:
        return _swirl_stills[key]
    values = {**swirl.PARAMS, **swirl.colour_values(ground_hue(ground))}
    centre = (target.width() / 2.0, target.height() / 2.0)
    try:
        image = field.render(swirl.STILL_T, target, values, centre, 1.0)
    except Exception as error:
        log.warning("The swirl ground could not render a still (%s); drawing Aura", error)
        return None
    _swirl_stills[key] = image
    return image


def paint_ground(painter, rect, ground, ratio, image=None):
    """Paint an already drawn()-resolved ground into rect, still. image is its decoded picture"""
    rect = QRectF(rect)
    if ground.style == "solid":
        painter.fillRect(rect, QColor(ground.color))
    elif ground.style == "checkerboard":
        _paint_checkerboard(painter, rect, ground)
    elif ground.style == "swirl":
        _paint_swirl(painter, rect, ground, ratio)
    elif ground.style == "image":
        _paint_image(painter, rect, ground, ratio, image)
    else:
        _paint_aura(painter, rect, ground)


def _paint_aura(painter, rect, ground):
    radius = math.hypot(rect.width(), rect.height()) / 2
    painter.fillRect(rect, QBrush(aura_gradient(ground_hue(ground), rect.center(), radius)))


def _paint_checkerboard(painter, rect, ground):
    square = max(1, round(max(rect.width(), rect.height()) / CHECKERBOARD_SQUARES_ACROSS))
    painter.save()
    painter.setBrushOrigin(rect.topLeft())
    painter.fillRect(rect, QBrush(checkerboard_tile(ground.checkerboard_color, square)))
    painter.restore()


def _paint_swirl(painter, rect, ground, ratio):
    size = QSize(math.ceil(rect.width()), math.ceil(rect.height()))
    still = swirl_still(ground, size, ratio) if not size.isEmpty() else None
    if still is None:
        _paint_aura(painter, rect, ground)
        return
    painter.save()
    # Bilinear, as the canvas draws it
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawImage(rect, still)
    painter.restore()


def _paint_image(painter, rect, ground, ratio, image):
    if image is None or image.isNull():
        painter.fillRect(rect, QColor(ground.fill))
        return
    size = QSize(round(rect.width() * ratio), round(rect.height() * ratio))
    if size.isEmpty():
        return
    positioning = "crop" if ground.positioning in _MINIATURE_AS_CROP else ground.positioning
    source = image_ground.flatten(image, ground.fill)
    composed = image_ground.compose(source, size, positioning, ground.fill)
    painter.drawImage(rect, composed, QRectF(QRect(0, 0, size.width(), size.height())))
