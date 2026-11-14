"""Fusion, finished where it still looks dated: the Mac's widget style

A proxy rather than an app stylesheet: any app stylesheet puts every widget under
QStyleSheetStyle, which stops a label inheriting its parent's font, so the reading size
never reached the Esoterica prose. Nothing else goes here; a fix for one widget belongs on
that widget.
"""

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPalette
from PyQt6.QtWidgets import QProxyStyle, QStyle, QStyleFactory

CC = QStyle.ComplexControl
SC = QStyle.SubControl
PM = QStyle.PixelMetric
PE = QStyle.PrimitiveElement

SCROLLBAR_EXTENT = 10
HANDLE_INSET = 2
HANDLE_MIN = 24
HANDLE_RADIUS = 3
HANDLE_ALPHA = 0.30
HANDLE_HOVER_ALPHA = 0.50
# Plasma's tabs show a plain cross; Breeze's tab-close is a document with a red one
TAB_CLOSE_ICON = "window-close"


def handle_colour(palette, hovered):
    colour = QColor(palette.color(QPalette.ColorRole.WindowText))
    colour.setAlphaF(HANDLE_HOVER_ALPHA if hovered else HANDLE_ALPHA)
    return colour


def _slider_rect(option):
    """The handle's span of the whole bar: a scrollbar here has no arrow buttons"""
    groove = option.rect
    horizontal = option.orientation == Qt.Orientation.Horizontal
    length = groove.width() if horizontal else groove.height()
    span = option.maximum - option.minimum
    whole = span + option.pageStep
    handle = length * option.pageStep // whole if span > 0 else length
    handle = min(length, max(HANDLE_MIN, handle))
    offset = QStyle.sliderPositionFromValue(
        option.minimum, option.maximum, option.sliderPosition, length - handle, option.upsideDown
    )
    if horizontal:
        return QRect(groove.x() + offset, groove.y(), handle, groove.height())
    return QRect(groove.x(), groove.y() + offset, groove.width(), handle)


class BreezeFusionStyle(QProxyStyle):
    """Fusion with Breeze's thin, arrowless scrollbars and plain tab close cross"""

    def pixelMetric(self, metric, option=None, widget=None):
        if metric == PM.PM_ScrollBarExtent:
            return SCROLLBAR_EXTENT
        if metric == PM.PM_ScrollBarSliderMin:
            return HANDLE_MIN
        return super().pixelMetric(metric, option, widget)

    def subControlRect(self, control, option, sub, widget=None):
        if control != CC.CC_ScrollBar:
            return super().subControlRect(control, option, sub, widget)
        groove = option.rect
        slider = _slider_rect(option)
        horizontal = option.orientation == Qt.Orientation.Horizontal
        if sub in (SC.SC_ScrollBarAddLine, SC.SC_ScrollBarSubLine):
            rect = QRect()
        elif sub == SC.SC_ScrollBarSlider:
            rect = slider
        elif sub == SC.SC_ScrollBarSubPage:
            rect = (
                QRect(groove.topLeft(), slider.bottomLeft()).adjusted(0, 0, -1, 0)
                if horizontal
                else QRect(groove.topLeft(), slider.topRight()).adjusted(0, 0, 0, -1)
            )
        elif sub == SC.SC_ScrollBarAddPage:
            rect = (
                QRect(slider.topRight(), groove.bottomRight()).adjusted(1, 0, 0, 0)
                if horizontal
                else QRect(slider.bottomLeft(), groove.bottomRight()).adjusted(0, 1, 0, 0)
            )
        else:  # groove, first, last
            rect = QRect(groove)
        if horizontal:
            rect = QStyle.visualRect(option.direction, groove, rect)
        return rect

    def drawComplexControl(self, control, option, painter, widget=None):
        if control != CC.CC_ScrollBar:
            super().drawComplexControl(control, option, painter, widget)
            return
        if option.maximum == option.minimum:
            return  # nothing to scroll: a bare trough
        hovered = bool(option.state & QStyle.StateFlag.State_Sunken) or (
            bool(option.state & QStyle.StateFlag.State_MouseOver)
            and bool(option.activeSubControls & SC.SC_ScrollBarSlider)
        )
        rect = QRectF(self.subControlRect(control, option, SC.SC_ScrollBarSlider, widget))
        inset = HANDLE_INSET
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(handle_colour(option.palette, hovered))
        painter.drawRoundedRect(
            rect.adjusted(inset, inset, -inset, -inset), HANDLE_RADIUS, HANDLE_RADIUS
        )
        painter.restore()

    def drawPrimitive(self, element, option, painter, widget=None):
        if element != PE.PE_IndicatorTabClose:
            super().drawPrimitive(element, option, painter, widget)
            return
        state = option.state
        painter.save()
        if state & QStyle.StateFlag.State_MouseOver and state & QStyle.StateFlag.State_Enabled:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(handle_colour(option.palette, hovered=False))
            painter.drawRoundedRect(QRectF(option.rect), HANDLE_RADIUS, HANDLE_RADIUS)
        mode = QIcon.Mode.Normal if state & QStyle.StateFlag.State_Enabled else QIcon.Mode.Disabled
        QIcon.fromTheme(TAB_CLOSE_ICON).paint(
            painter, option.rect, Qt.AlignmentFlag.AlignCenter, mode
        )
        painter.restore()


def breeze_fusion():
    """A fresh style each time: QApplication.setStyle takes and deletes the last one"""
    return BreezeFusionStyle(QStyleFactory.create("Fusion"))
