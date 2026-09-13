"""An empty view's explanation: an icon, a heading, a sentence or two and a footnote.

After Kirigami's PlaceholderMessage (controls/PlaceholderMessage.qml) in its
Informational form. It has no action, so every element takes the muted text colour,
except links, which keep the palette's link colour: they're the one thing to act on.
"""

from PyQt6.QtCore import QEvent, QPointF, QRect, Qt
from PyQt6.QtGui import QFont, QIcon, QImage, QPainter
from PyQt6.QtWidgets import QLabel, QSizePolicy, QStyle, QVBoxLayout, QWidget

from tarot_canvas.ui.palette import muted_text, with_text_colour

# Kirigami's iconSizes.huge * 1.5 (PlaceholderMessage.qml:198)
ICON_SIZE = 96
HEADING_SCALE = 1.35
FOOTNOTE_SCALE = 0.85
EXPLANATION_WIDTH_EMS = 32


def tint_icon(icon, logical_size, dpr, colour):
    """`icon` at `logical_size` logical px, every pixel it covers recoloured to `colour`.

    Breeze's glyphs are dark lines drawn for a light ground; Kirigami recolours them
    to the text colour so they survive a dark theme, and so does this.
    """
    side = round(logical_size * dpr)
    image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    icon.paint(painter, QRect(0, 0, side, side))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(image.rect(), colour)
    painter.end()
    image.setDevicePixelRatio(dpr)
    return image


def _layout_spacing(style):
    spacing = style.pixelMetric(QStyle.PixelMetric.PM_LayoutVerticalSpacing)
    if spacing < 0:  # the style spaces by control type instead
        spacing = style.layoutSpacing(
            QSizePolicy.ControlType.Label, QSizePolicy.ControlType.Label, Qt.Orientation.Vertical
        )
    return max(spacing, 0)


def _scaled(font, scale):
    font = QFont(font)
    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() * scale)
    else:
        font.setPixelSize(round(font.pixelSize() * scale))
    return font


class TintedIcon(QWidget):
    """`icon` at a fixed logical size, in `colour(palette)`, drawn at the screen's dpr.

    It tints at paint time, so a theme or screen change needs only the repaint Qt already
    does on PaletteChange.
    """

    def __init__(self, icon, logical_size, colour=muted_text, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.logical_size = logical_size
        self.colour = colour
        self.setFixedSize(logical_size, logical_size)

    def paintEvent(self, event):
        image = tint_icon(
            self.icon, self.logical_size, self.devicePixelRatioF(), self.colour(self.palette())
        )
        painter = QPainter(self)
        painter.drawImage(QPointF(0, 0), image)
        painter.end()


class _WrappedLabel(QLabel):
    """A word-wrapped label that is sized and laid out at the same width.

    QBoxLayout sizes an item's height by heightForWidth(the column's full width), but lays an
    AlignHCenter item out at its sizeHint width, which for a wrapping QLabel is a guess at a
    short line. The two disagree and the text is cut off, worst when the view is wide. Here
    both are min(available, maximumWidth).
    """

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(self.maximumWidth())  # the layout bounds it to what's available
        return hint

    def heightForWidth(self, width):
        return super().heightForWidth(min(width, self.maximumWidth()))


class PlaceholderMessage(QWidget):
    """Why a view is empty. An empty `text`, `explanation` or `footnote` hides its label.

    The explanation and the footnote may carry `<a href>` links, which open in the browser.
    """

    def __init__(self, icon_name, text="", explanation="", footnote="", parent=None):
        super().__init__(parent)
        # No substitute: a theme without the icon gets no icon
        self.icon = QIcon.fromTheme(icon_name) if QIcon.hasThemeIcon(icon_name) else None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2 * _layout_spacing(self.style()))

        self.icon_slot = None
        if self.icon is not None:
            self.icon_slot = TintedIcon(self.icon, ICON_SIZE, parent=self)
            layout.addWidget(self.icon_slot, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.heading = _WrappedLabel(text, self)
        self.explanation = _WrappedLabel(explanation, self)
        self.footnote = _WrappedLabel(footnote, self)
        for label in self._labels():
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setHidden(not label.text())
            layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignHCenter)
        for label in (self.explanation, self.footnote):
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.LinksAccessibleByMouse
                | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
            )

        # Not Maximum: that caps the height at sizeHint, which is measured at the full column
        # width, so any narrower view cuts the text off. The layout sizes it by heightForWidth.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._apply_fonts()
        self._apply_colours()

    def _labels(self):
        return (self.heading, self.explanation, self.footnote)

    def _apply_fonts(self):
        heading = _scaled(self.font(), HEADING_SCALE)
        heading.setBold(False)
        self.heading.setFont(heading)
        self.footnote.setFont(_scaled(self.font(), FOOTNOTE_SCALE))

        # One column width for every label, measured in the explanation's font
        em = self.explanation.fontMetrics().horizontalAdvance("M")
        for label in self._labels():
            label.setMaximumWidth(em * EXPLANATION_WIDTH_EMS)

    def _apply_colours(self):
        colour = muted_text(self.palette())
        for label in self._labels():
            label.setPalette(with_text_colour(label.palette(), colour))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_colours()
        elif event.type() == QEvent.Type.FontChange:
            self._apply_fonts()
