"""Arrange on Arc: a panel over a corner of the canvas that previews its arc as it changes."""

from itertools import pairwise

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPalette
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSlider,
    QStyle,
    QStyleOption,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas.alignment import (
    arrange_items_on_arc,
    centre_of,
    measured_gap,
    set_turn,
)
from tarot_canvas.ui.strings import CANVAS

STEP = 15  # degrees per notch of the bend and turn sliders
BEND_LIMIT = 360  # either way: a ring bowed up or down
TURN_LIMIT = 180
GAP_STEPS = 100  # notches of the spacing slider, 0.00 to 1.00 card widths

# What a tab's first arc starts from; later ones start from the last
ARC_DEFAULTS = {"bend": 180, "turn": 0, "clockwise": True, "follow": False}


# Kirigami's cornerRadius, which Breeze's frames share
CORNER_RADIUS = 5
# How far the outline is mixed from the window's colour toward its text's
OUTLINE_MIX = 0.2

# Where the panel may sit, in the order a tie is broken
CORNERS = ("top_right", "top_left", "bottom_right", "bottom_left")


def signed(degrees):
    """`degrees` with its sign, since which way a bend or turn goes matters: +15, 0, -15"""
    return f"{degrees:+d}" if degrees else "0"


def window_margin(style):
    """The style's margin for a window's contents, which a panel over the canvas also gets"""
    option = QStyleOption()
    option.state |= QStyle.StateFlag.State_Window
    return style.pixelMetric(QStyle.PixelMetric.PM_LayoutLeftMargin, option)


def outline_colour(palette):
    """A line that stands out from the panel's fill, in a dark scheme as in a light one"""
    fill = palette.color(QPalette.ColorRole.Window)
    text = palette.color(QPalette.ColorRole.WindowText)
    return QColor.fromRgbF(
        *(
            f + (t - f) * OUTLINE_MIX
            for f, t in zip(fill.getRgbF()[:3], text.getRgbF()[:3], strict=True)
        )
    )


def _plain_label(text):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class ArcPopover(QFrame):
    applied = pyqtSignal()
    closed = pyqtSignal(dict)  # the settings to start from next time
    previewed = pyqtSignal()  # the cards have moved

    def __init__(self, items, settings, view, parent):
        super().__init__(parent)
        # Painted opaque by paintEvent, with an outline, whatever the canvas under it is
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.view = view
        self.items = list(items)
        self.snapshot = [(item, QPointF(item.pos()), item.orient) for item in self.items]
        self.centroid = centre_of(self.items)
        self.corner = CORNERS[0]
        self.finished = False

        settings = {**ARC_DEFAULTS, **settings}
        gap = min(max(round(measured_gap(self.items), 2), 0.0), 1.0)

        self.bend = self._slider(-BEND_LIMIT // STEP, BEND_LIMIT // STEP, settings["bend"] // STEP)
        self.turn = self._slider(-TURN_LIMIT // STEP, TURN_LIMIT // STEP, settings["turn"] // STEP)
        self.spacing = self._slider(0, GAP_STEPS, round(gap * GAP_STEPS))
        self.spacing_box = self._spin_box(self.spacing)

        self.clockwise = QRadioButton(CANVAS["arc_clockwise"])
        self.anticlockwise = QRadioButton(CANVAS["arc_anticlockwise"])
        self.direction = self._choice(self.clockwise, self.anticlockwise, settings["clockwise"])
        self.upright = QRadioButton(CANVAS["arc_upright"])
        self.follow = QRadioButton(CANVAS["arc_follow"])
        self.cards = self._choice(self.upright, self.follow, not settings["follow"])

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        self.buttons.rejected.connect(self.cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)

        # The menu entry's label, echoed as a dialog's title would be
        self.title = _plain_label(CANVAS["arrange_arc"])
        typography.apply(self.title, typography.Role.HEADING_4)

        # Label, control, value: the sliders share a column, so they line up
        grid = QGridLayout()
        rows = (
            (CANVAS["arc_cards"], self._row(self.upright, self.follow), None),
            (CANVAS["arc_bend"], self.bend, self._value_label(self.bend, self._degrees_text)),
            (CANVAS["arc_turn"], self.turn, self._value_label(self.turn, self._degrees_text)),
            (CANVAS["arc_direction"], self._row(self.clockwise, self.anticlockwise), None),
            # Gross by the slider, fine by the spin box (the HIG's pairing)
            (CANVAS["arc_spacing"], self.spacing, self.spacing_box),
        )
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for row, (label, control, trailing) in enumerate(rows):
            grid.addWidget(_plain_label(label), row, 0, right)
            if trailing is None:
                grid.addLayout(control, row, 1, 1, 2)
            else:
                grid.addWidget(control, row, 1)
                grid.addWidget(trailing, row, 2)
        grid.setColumnStretch(1, 1)

        layout = QVBoxLayout(self)
        margin = window_margin(self.style())
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.addWidget(self.title)
        layout.addLayout(grid)
        # A gap between groups, twice the one between rows
        layout.addSpacing(layout.spacing())
        layout.addWidget(self.buttons)

        # Tab goes top to bottom, as the rows read, not in the order they were made
        chain = (
            self.upright,
            self.follow,
            self.bend,
            self.turn,
            self.clockwise,
            self.anticlockwise,
            self.spacing,
            self.spacing_box,
            *self.buttons.buttons(),
        )
        for first, second in pairwise(chain):
            QWidget.setTabOrder(first, second)

        for slider in (self.bend, self.turn, self.spacing):
            slider.valueChanged.connect(self.preview)
        for group in (self.direction, self.cards):
            group.idToggled.connect(lambda _id, checked: checked and self.preview())

        self.hide()

    # -- building ----------------------------------------------------------

    def _slider(self, low, high, value):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setPageStep(1)
        slider.setValue(min(max(value, low), high))
        return slider

    def _choice(self, first, second, first_checked):
        group = QButtonGroup(self)
        group.addButton(first, 0)
        group.addButton(second, 1)
        (first if first_checked else second).setChecked(True)
        return group

    def _row(self, *widgets):
        row = QHBoxLayout()
        for widget in widgets:
            row.addWidget(widget)
        row.addStretch()
        return row

    def _value_label(self, slider, text):
        """A slider's value, wide enough for any value it can show"""
        value = _plain_label(text(slider.value()))
        metrics = value.fontMetrics()
        value.setMinimumWidth(
            max(
                metrics.horizontalAdvance(text(n))
                for n in range(slider.minimum(), slider.maximum() + 1)
            )
        )
        slider.valueChanged.connect(lambda n: value.setText(text(n)))
        return value

    def _degrees_text(self, notch):
        return CANVAS["arc_degrees"].format(degrees=signed(notch * STEP))

    def _spin_box(self, slider):
        """A spin box over the slider's range in card widths, each following the other"""
        box = QDoubleSpinBox()
        box.setDecimals(2)
        box.setRange(slider.minimum() / GAP_STEPS, slider.maximum() / GAP_STEPS)
        box.setSingleStep(1 / GAP_STEPS)
        box.setValue(slider.value() / GAP_STEPS)
        prefix, _, suffix = CANVAS["arc_gap"].partition("{gap}")
        box.setPrefix(prefix)
        box.setSuffix(suffix)
        slider.valueChanged.connect(lambda notch: box.setValue(notch / GAP_STEPS))
        box.valueChanged.connect(lambda value: slider.setValue(round(value * GAP_STEPS)))
        return box

    # -- state -------------------------------------------------------------

    def settings(self):
        return {
            "bend": self.bend.value() * STEP,
            "turn": self.turn.value() * STEP,
            "clockwise": self.clockwise.isChecked(),
            "follow": self.follow.isChecked(),
        }

    def gap(self):
        return self.spacing.value() / GAP_STEPS

    def _arrange(self):
        """Arrange from where the cards were when the panel opened"""
        arrange_items_on_arc(self.items, **self.settings(), gap=self.gap(), centroid=self.centroid)

    def preview(self):
        if self.finished:
            return
        self._arrange()
        self.previewed.emit()

    def restore(self):
        for item, pos, orient in self.snapshot:
            item.setPos(pos)
            set_turn(item, orient)

    def cards_rect(self):
        """The arranged cards' bounds in the scene"""
        rect = self.items[0].sceneBoundingRect()
        for item in self.items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        return rect

    # -- where it sits -----------------------------------------------------

    def _viewport_rect(self):
        """The view's viewport, in the coordinates of the panel's parent"""
        viewport = self.view.viewport()
        return QRect(viewport.mapTo(self.parentWidget(), QPoint(0, 0)), viewport.size())

    def _corner_rect(self, corner):
        """Where the panel goes at `corner`, in its parent's coordinates"""
        inset = window_margin(self.style())
        area = self._viewport_rect().adjusted(inset, inset, -inset, -inset)
        rect = QRect(QPoint(0, 0), self.size())
        if corner.startswith("top"):
            rect.moveTop(area.top())
        else:
            rect.moveBottom(area.bottom())
        if corner.endswith("left"):
            rect.moveLeft(area.left())
        else:
            rect.moveRight(area.right())
        return rect

    def _choose_corner(self):
        """The corner that hides least of the arranged cards; top right on a tie"""
        cards = self.view.mapFromScene(self.cards_rect()).boundingRect()
        cards.translate(self._viewport_rect().topLeft())

        def hidden(corner):
            overlap = self._corner_rect(corner).intersected(cards)
            return 0 if overlap.isEmpty() else overlap.width() * overlap.height()

        return min(CORNERS, key=hidden)

    def place(self):
        self.setGeometry(self._corner_rect(self.corner))

    def free_region(self):
        """The part of the viewport the panel leaves clear, in viewport coordinates:
        the larger of the strips beside it and below or above it"""
        viewport = QRect(QPoint(0, 0), self.view.viewport().size())
        panel = self.geometry().translated(-self._viewport_rect().topLeft())
        beside = QRect(viewport)
        if self.corner.endswith("left"):
            beside.setLeft(panel.right() + 1)
        else:
            beside.setRight(panel.left() - 1)
        across = QRect(viewport)
        if self.corner.startswith("top"):
            across.setTop(panel.bottom() + 1)
        else:
            across.setBottom(panel.top() - 1)

        def area(rect):
            return max(rect.width(), 0) * max(rect.height(), 0)

        return beside if area(beside) >= area(across) else across

    # -- opening and closing -----------------------------------------------

    def open(self):
        """Show the first preview, then the panel in the corner that hides least of it"""
        self.ensurePolished()
        self.layout().activate()
        self.adjustSize()
        self._arrange()
        self.corner = self._choose_corner()
        self.place()
        self.view.installEventFilter(self)
        self.show()
        self.raise_()
        self.previewed.emit()

    def eventFilter(self, watched, event):
        if watched is self.view and event.type() == QEvent.Type.Resize:
            self.place()
        return False

    def apply(self):
        self._finish(applied=True)

    def cancel(self):
        self._finish(applied=False)

    def _finish(self, applied):
        if self.finished:
            return
        self.finished = True
        if not applied:
            self.restore()
        self.view.removeEventFilter(self)
        self.hide()
        self.closed.emit(self.settings())
        if applied:
            self.applied.emit()

    def hideEvent(self, event):
        super().hideEvent(event)
        # Hidden other than by Apply or Cancel (its tab closed, say): nothing was applied
        if not event.spontaneous():
            self.cancel()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.apply()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(outline_colour(self.palette()))
        painter.setBrush(self.palette().color(QPalette.ColorRole.Window))
        # Half a pixel in, so the 1px outline falls on whole pixels
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), CORNER_RADIUS, CORNER_RADIUS
        )
