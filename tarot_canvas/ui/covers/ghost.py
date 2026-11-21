"""Covers for decks that aren't installed yet."""

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSizeF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon

from tarot_canvas.ui import units

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


def paint_placeholder_well(
    painter,
    well,
    palette,
    icon="image-missing",
    *,
    icon_fraction=PLACEHOLDER_ICON_FRACTION,
    icon_opacity=1.0,
):
    """A well the same footprint as real art; icon is a theme name or a QIcon"""
    painter.save()
    ground = QColor(palette.text().color())
    ground.setAlpha(PLACEHOLDER_WELL_ALPHA)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ground)
    painter.drawRoundedRect(well, units.COVER_RADIUS, units.COVER_RADIUS)

    if not isinstance(icon, QIcon):
        icon = QIcon.fromTheme(icon)
    if not icon.isNull():
        extent = max(16, round(min(well.width(), well.height()) * icon_fraction))
        target = QRect(0, 0, extent, extent)
        target.moveCenter(well.center())
        painter.setOpacity(painter.opacity() * icon_opacity)
        icon.paint(painter, target, Qt.AlignmentFlag.AlignCenter, QIcon.Mode.Disabled)
    painter.restore()


def paint_ghost_cover(
    painter,
    rect,
    pixmap,
    *,
    progress=None,
    failed=False,
    emblem=None,
    palette=None,
    ground=None,
    dimmed=True,
):
    """Dimmed art + progress bar + download icon"""
    palette = palette or QGuiApplication.palette()
    cover = QRect(rect)
    painter.save()

    if pixmap is not None and not pixmap.isNull():
        size = pixmap.deviceIndependentSize().scaled(
            QSizeF(cover.size()), Qt.AspectRatioMode.KeepAspectRatio
        )
        target = QRectF(QPointF(0, 0), size)
        target.moveCenter(QRectF(cover).center())
        painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        if dimmed:
            veil = QColor(ground if ground is not None else palette.window().color())
            veil.setAlpha(round(255 * (1 - GHOST_OPACITY)))
            painter.fillRect(target, veil)
        cover = target.toAlignedRect()

    emblem_bottom = cover.bottom()
    if progress is not None:
        emblem_bottom = _paint_bar(painter, cover, progress, palette) - 1

    icon = QIcon.fromTheme("dialog-error") if failed else emblem
    paint_emblem(painter, cover, icon, palette, emblem_bottom)

    painter.restore()


def paint_emblem(painter, cover, icon, palette, bottom=None):
    """icon in a circle in cover's bottom-right corner, above bottom if given"""
    if icon is None or icon.isNull():
        return
    bottom = cover.bottom() if bottom is None else bottom
    extent = max(EMBLEM_MIN, round(min(cover.width(), cover.height()) * EMBLEM_FRACTION))
    plate = QRect(0, 0, extent, extent)
    plate.moveBottomRight(QPoint(cover.right() - EMBLEM_MARGIN, bottom - EMBLEM_MARGIN))
    painter.save()
    ground = QColor(palette.window().color())
    ground.setAlpha(EMBLEM_PLATE_ALPHA)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ground)
    painter.drawEllipse(plate)

    extent = round(plate.width() * EMBLEM_GLYPH_FRACTION)
    glyph = QRect(0, 0, extent, extent)
    glyph.moveCenter(plate.center())
    icon.paint(painter, glyph)
    painter.restore()


def _paint_bar(painter, cover, progress, palette):
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
