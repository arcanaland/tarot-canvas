"""Arrange on Arc: a panel over a corner of the canvas that previews its arc as it changes."""

from itertools import pairwise

from PyQt6.QtCore import QPoint, QPointF, QRect, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QRadioButton,
    QSlider,
    QWidget,
)

from tarot_canvas.ui.canvas.alignment import (
    arrange_items_on_arc,
    centre_of,
    measured_gap,
    set_turn,
)
from tarot_canvas.ui.canvas.canvas_panel import CanvasPanel, plain_label
from tarot_canvas.ui.strings import CANVAS

STEP = 15  # degrees per notch of the bend and turn sliders
BEND_LIMIT = 360  # either way: a ring bowed up or down
TURN_LIMIT = 180
GAP_STEPS = 100  # notches of the spacing slider, 0.00 to 1.00 card widths

# What a tab's first arc starts from; later ones start from the last
ARC_DEFAULTS = {"bend": 180, "turn": 0, "clockwise": True, "follow": False}


def signed(degrees):
    """`degrees` with its sign, since which way a bend or turn goes matters: +15, 0, -15"""
    return f"{degrees:+d}" if degrees else "0"


class ArcPopover(CanvasPanel):
    previewed = pyqtSignal()  # the cards have moved

    def __init__(self, items, settings, view, parent):
        super().__init__(CANVAS["arrange_arc"], view, parent)
        self.items = list(items)
        self.snapshot = [(item, QPointF(item.pos()), item.orient) for item in self.items]
        self.centroid = centre_of(self.items)

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
            grid.addWidget(plain_label(label), row, 0, right)
            if trailing is None:
                grid.addLayout(control, row, 1, 1, 2)
            else:
                grid.addWidget(control, row, 1)
                grid.addWidget(trailing, row, 2)
        grid.setColumnStretch(1, 1)

        self.lay_out(grid)

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
        value = plain_label(text(slider.value()))
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

    def covered_rect(self):
        return self.cards_rect()

    def cards_rect(self):
        """The arranged cards' bounds in the scene"""
        rect = self.items[0].sceneBoundingRect()
        for item in self.items[1:]:
            rect = rect.united(item.sceneBoundingRect())
        return rect

    # -- where it sits -----------------------------------------------------

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

    # -- opening ----------------------------------------------------------

    def open(self):
        """Show the first preview, then the panel in the corner that hides least of it"""
        self._arrange()
        super().open()
        self.previewed.emit()
