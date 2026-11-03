"""Arrange on Arc: a popover under the Align button that previews its arc on the canvas."""

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSlider,
    QStyle,
    QStyleOption,
    QVBoxLayout,
)

from tarot_canvas.ui.canvas.alignment import (
    arrange_items_on_arc,
    centre_of,
    measured_gap,
    set_turn,
)
from tarot_canvas.ui.strings import CANVAS
from tarot_canvas.ui.widgets.contextual_help import placed

STEP = 15  # degrees per notch of the sweep and start sliders
GAP_STEPS = 100  # notches of the spacing slider, 0.00 to 1.00 card widths

# What a tab's first arc starts from; later ones start from the last
ARC_DEFAULTS = {"sweep": 360, "start": 90, "clockwise": True, "follow": False}


def clock(degrees):
    """`degrees` clockwise from 12 o'clock as an (hour, minute) on a clock face"""
    minutes = round(degrees * 2) % 720
    return minutes // 60 or 12, minutes % 60


def _plain_label(text):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class ArcPopover(QFrame):
    """Sweep, start, direction, upright or follow, and spacing, previewed as they change.

    Apply keeps the preview. Cancel, Esc and a click elsewhere put every card back.
    """

    applied = pyqtSignal()
    closed = pyqtSignal(dict)  # the settings to start from next time

    def __init__(self, items, settings, button=None, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.button = button
        self.items = list(items)
        self.snapshot = [(item, QPointF(item.pos()), item.orient) for item in self.items]
        self.centroid = centre_of(self.items)
        self._applied = False
        self._finished = False

        settings = {**ARC_DEFAULTS, **settings}
        gap = min(max(round(measured_gap(self.items), 2), 0.0), 1.0)

        self.sweep = self._slider(1, 360 // STEP, settings["sweep"] // STEP)
        self.start = self._slider(0, 360 // STEP - 1, settings["start"] // STEP)
        self.spacing = self._slider(0, GAP_STEPS, round(gap * GAP_STEPS))

        self.clockwise = QRadioButton(CANVAS["arc_clockwise"])
        self.anticlockwise = QRadioButton(CANVAS["arc_anticlockwise"])
        self.direction = self._choice(self.clockwise, self.anticlockwise, settings["clockwise"])
        self.upright = QRadioButton(CANVAS["arc_upright"])
        self.follow = QRadioButton(CANVAS["arc_follow"])
        self.cards = self._choice(self.upright, self.follow, not settings["follow"])

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        self.buttons.rejected.connect(self.close)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)

        form = QFormLayout()
        form.addRow(_plain_label(CANVAS["arc_sweep"]), self._valued(self.sweep, self._sweep_text))
        form.addRow(_plain_label(CANVAS["arc_start"]), self._valued(self.start, self._start_text))
        form.addRow(
            _plain_label(CANVAS["arc_direction"]), self._row(self.clockwise, self.anticlockwise)
        )
        form.addRow(_plain_label(CANVAS["arc_cards"]), self._row(self.upright, self.follow))
        form.addRow(
            _plain_label(CANVAS["arc_spacing"]), self._valued(self.spacing, self._spacing_text)
        )

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

        for slider in (self.sweep, self.start, self.spacing):
            slider.valueChanged.connect(self.preview)
        for group in (self.direction, self.cards):
            group.idToggled.connect(lambda _id, checked: checked and self.preview())

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

    def _valued(self, slider, text):
        """A slider with its value to its right, wide enough for any value it can show"""
        value = _plain_label(text(slider.value()))
        metrics = value.fontMetrics()
        value.setMinimumWidth(
            max(
                metrics.horizontalAdvance(text(n))
                for n in range(slider.minimum(), slider.maximum() + 1)
            )
        )
        slider.valueChanged.connect(lambda n: value.setText(text(n)))
        return self._row(slider, value)

    def _sweep_text(self, notch):
        return CANVAS["arc_degrees"].format(degrees=notch * STEP)

    def _start_text(self, notch):
        hour, minute = clock(notch * STEP)
        return CANVAS["arc_clock"].format(hour=hour, minute=f"{minute:02d}")

    def _spacing_text(self, notch):
        return CANVAS["arc_gap"].format(gap=f"{notch / GAP_STEPS:.2f}")

    # -- state -------------------------------------------------------------

    def settings(self):
        return {
            "sweep": self.sweep.value() * STEP,
            "start": self.start.value() * STEP,
            "clockwise": self.clockwise.isChecked(),
            "follow": self.follow.isChecked(),
        }

    def gap(self):
        return self.spacing.value() / GAP_STEPS

    def preview(self):
        """Arrange from where the cards were when the popover opened"""
        arrange_items_on_arc(self.items, **self.settings(), gap=self.gap(), centroid=self.centroid)

    def restore(self):
        for item, pos, orient in self.snapshot:
            item.setPos(pos)
            set_turn(item, orient)

    def apply(self):
        self._applied = True
        self.close()

    # -- showing and closing -----------------------------------------------

    def open_at(self, anchor):
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay, False)
        self.ensurePolished()
        self.layout().activate()
        self.adjustSize()
        screen = (self.button or self).screen().availableGeometry()
        self.move(placed(anchor, self.size(), screen))
        self.show()
        self.sweep.setFocus()
        self.preview()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._finished:
            return
        self._finished = True
        if not self._applied:
            self.restore()
        self.closed.emit(self.settings())
        if self._applied:
            self.applied.emit()

    def mousePressEvent(self, event):
        # A click on the Align button closes the popover, and doesn't reopen the menu
        button = self.button
        if button is not None and button.rect().contains(
            button.mapFromGlobal(event.globalPosition().toPoint())
        ):
            self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        option = QStyleOption()
        option.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_PanelMenu, option, painter, self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_FrameMenu, option, painter, self)
