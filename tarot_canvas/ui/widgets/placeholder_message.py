from PyQt6.QtCore import QEvent, QPointF, QRect, Qt
from PyQt6.QtGui import (
    QGuiApplication,
    QIcon,
    QIconEngine,
    QImage,
    QPainter,
    QPalette,
    QPixmap,
)
from PyQt6.QtWidgets import QLabel, QPushButton, QSizePolicy, QStyle, QVBoxLayout, QWidget

from tarot_canvas.ui import typography
from tarot_canvas.ui.palette import muted_text, with_text_colour

# Kirigami's iconSizes.huge * 1.5 (PlaceholderMessage.qml:198)
ICON_SIZE = 96
EXPLANATION_WIDTH_EMS = 32


def tint_icon(icon, logical_size, dpr, colour):
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


class _TintedEngine(QIconEngine):
    """An icon file drawn in the application palette's text colour, as a monochrome theme
    icon is, so it follows a light or dark colour scheme"""

    def __init__(self, path):
        super().__init__()
        self._path = str(path)
        self._icon = QIcon(self._path)

    def _colour(self, mode):
        palette = QGuiApplication.palette()
        if mode == QIcon.Mode.Selected:
            return palette.color(QPalette.ColorRole.HighlightedText)
        if mode == QIcon.Mode.Disabled:
            return palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
        return palette.color(QPalette.ColorRole.Text)

    def paint(self, painter, rect, mode, state):
        device = painter.device()
        dpr = device.devicePixelRatioF() if device is not None else 1.0
        side = min(rect.width(), rect.height())
        target = QRect(0, 0, side, side)
        target.moveCenter(rect.center())
        painter.drawImage(target, tint_icon(self._icon, side, dpr, self._colour(mode)))

    def pixmap(self, size, mode, state):
        return self.scaledPixmap(size, mode, state, 1.0)

    def scaledPixmap(self, size, mode, state, scale):
        side = min(size.width(), size.height())
        image = tint_icon(self._icon, side, scale, self._colour(mode))
        return QPixmap.fromImage(image)

    def clone(self):
        return _TintedEngine(self._path)


def tinted_icon(path):
    """A QIcon of an app's own monochrome file that takes the text colour"""
    return QIcon(_TintedEngine(path))


def _layout_spacing(style):
    spacing = style.pixelMetric(QStyle.PixelMetric.PM_LayoutVerticalSpacing)
    if spacing < 0:  # the style spaces by control type instead
        spacing = style.layoutSpacing(
            QSizePolicy.ControlType.Label, QSizePolicy.ControlType.Label, Qt.Orientation.Vertical
        )
    return max(spacing, 0)


class TintedIcon(QWidget):
    """fixed logical size drawn at the screen's dpr"""

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
    """A word-wrapped label that is sized and laid out at the same width."""

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(self.maximumWidth())  # the layout bounds it to what's available
        return hint

    def heightForWidth(self, width):
        return super().heightForWidth(min(width, self.maximumWidth()))


class PlaceholderMessage(QWidget):
    def __init__(
        self, icon, text="", explanation="", footnote="", parent=None, helpful_action=None
    ):
        super().__init__(parent)
        # A theme icon name or a QIcon of our own. No substitute: a theme without the icon
        # gets no icon
        if isinstance(icon, str):
            icon = QIcon.fromTheme(icon) if QIcon.hasThemeIcon(icon) else None
        self.icon = icon

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
        # A placeholder string's tags are shown, not parsed
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        for label in (self.explanation, self.footnote):
            label.setOpenExternalLinks(True)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.LinksAccessibleByMouse
                | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
            )

        # Kirigami's helpfulAction: the one thing to do about the emptiness
        self.helpful_action = helpful_action
        self.helpful_button = None
        if helpful_action is not None:
            self.helpful_button = QPushButton(self)
            self.helpful_button.clicked.connect(helpful_action.trigger)
            helpful_action.changed.connect(self._sync_helpful_button)
            self._sync_helpful_button()
            layout.addWidget(self.helpful_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._apply_fonts()
        self._apply_colours()

    def _sync_helpful_button(self):
        action = self.helpful_action
        self.helpful_button.setText(action.text())
        self.helpful_button.setIcon(action.icon())
        self.helpful_button.setEnabled(action.isEnabled())
        self.helpful_button.setVisible(action.isVisible())

    def _labels(self):
        return (self.heading, self.explanation, self.footnote)

    def _apply_fonts(self):
        typography.apply(self.heading, typography.Role.HEADING_1)
        typography.apply(self.footnote, typography.Role.SMALL)

        # One column width for every label
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
