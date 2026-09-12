"""Covers for decks that aren't installed yet.

Nothing here knows about the library's model or delegate, so any widget can paint one.
"""

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSizeF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon

from tarot_canvas.ui.library import units

GHOST_OPACITY = 0.45

PLACEHOLDER_WELL_ALPHA = 20
PLACEHOLDER_ICON_FRACTION = 0.4

BAR_HEIGHT_FRACTION = 0.04
BAR_MIN_HEIGHT = 3
BAR_TRACK_ALPHA = 90

EMBLEM_FRACTION = 0.2
EMBLEM_MIN = 22
EMBLEM_MARGIN = 6
EMBLEM_GLYPH_FRACTION = 0.6
EMBLEM_PLATE_ALPHA = 220


def paint_placeholder_well(painter, well, palette):
    """A well the same footprint as real art"""
    painter.save()
    ground = QColor(palette.text().color())
    ground.setAlpha(PLACEHOLDER_WELL_ALPHA)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ground)
    painter.drawRoundedRect(well, units.COVER_RADIUS, units.COVER_RADIUS)

    icon = QIcon.fromTheme("image-missing")
    if not icon.isNull():
        extent = max(16, round(min(well.width(), well.height()) * PLACEHOLDER_ICON_FRACTION))
        target = QRect(0, 0, extent, extent)
        target.moveCenter(well.center())
        icon.paint(painter, target, Qt.AlignmentFlag.AlignCenter, QIcon.Mode.Disabled)
    painter.restore()


def paint_ghost_cover(
    painter, rect, pixmap, *, progress=None, failed=False, emblem=None, palette=None
):
    """Dimmed art, then a progress bar and an emblem at full strength.

    `rect` is the art's bounds; with a null pixmap the bar and emblem go inside it.
    """
    palette = palette or QGuiApplication.palette()
    cover = QRect(rect)
    painter.save()

    if pixmap is not None and not pixmap.isNull():
        size = pixmap.deviceIndependentSize().scaled(
            QSizeF(cover.size()), Qt.AspectRatioMode.KeepAspectRatio
        )
        target = QRectF(QPointF(0, 0), size)
        target.moveCenter(QRectF(cover).center())
        painter.setOpacity(GHOST_OPACITY)
        painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        painter.setOpacity(1.0)
        cover = target.toAlignedRect()

    emblem_bottom = cover.bottom()
    if progress is not None:
        emblem_bottom = _paint_bar(painter, cover, progress, palette) - 1

    icon = QIcon.fromTheme("dialog-error") if failed else emblem
    if icon is not None and not icon.isNull():
        extent = max(EMBLEM_MIN, round(min(cover.width(), cover.height()) * EMBLEM_FRACTION))
        plate = QRect(0, 0, extent, extent)
        plate.moveBottomRight(QPoint(cover.right() - EMBLEM_MARGIN, emblem_bottom - EMBLEM_MARGIN))
        _paint_emblem(painter, plate, icon, palette)

    painter.restore()


def _paint_emblem(painter, plate, icon, palette):
    """The icon on a disc, so a monochrome glyph reads over any art"""
    ground = QColor(palette.window().color())
    ground.setAlpha(EMBLEM_PLATE_ALPHA)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ground)
    painter.drawEllipse(plate)

    extent = round(plate.width() * EMBLEM_GLYPH_FRACTION)
    glyph = QRect(0, 0, extent, extent)
    glyph.moveCenter(plate.center())
    icon.paint(painter, glyph)


def _paint_bar(painter, cover, progress, palette):
    """A determinate bar across the bottom of the cover; returns its top."""
    fraction = min(1.0, max(0.0, float(progress)))
    height = max(BAR_MIN_HEIGHT, round(cover.height() * BAR_HEIGHT_FRACTION))
    track = QRect(cover.left(), cover.bottom() - height + 1, cover.width(), height)

    ground = QColor(palette.text().color())
    ground.setAlpha(BAR_TRACK_ALPHA)
    painter.fillRect(track, ground)

    filled = QRect(track)
    filled.setWidth(round(track.width() * fraction))
    if filled.width() > 0:
        painter.fillRect(filled, palette.highlight().color())
    return track.top()
