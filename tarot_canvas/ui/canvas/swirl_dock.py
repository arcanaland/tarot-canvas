"""The swirl's tuning dock, opened by swirl.DOCK_ENV. A developer tool: labels are names, not copy.

Knob edits change swirl.PARAMS and the edited GroundHue in place, live, and are never saved.
Copy puts both on the clipboard as Python, to paste back into swirl.py and ground.py.
"""

from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QRadialGradient
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QWidget,
)

from tarot_canvas.ui.canvas import swirl
from tarot_canvas.ui.canvas.ground import GROUND_HUES, ground_hue_id

# name: (minimum, maximum, step); an int step makes an int knob
RANGES = {
    "twirl": (0.0, 12.0, 0.05),
    "spin": (-1.0, 1.0, 0.005),
    "blooms": (0, swirl.MAX_BLOOMS, 1),
    "bloom": (0.0, 8.0, 0.05),
    "bloom_size": (0.1, 3.0, 0.01),
    "rounds": (1, 8, 1),
    "warp": (0.0, 2.0, 0.01),
    "contrast": (0.0, 1.5, 0.01),
    "speed": (0.0, 3.0, 0.01),
    "pixel": (1, 8, 1),
    "every": (1, 8, 1),
    "parallax_pan": (0.0, 1.0, 0.01),
    "parallax_zoom": (0.0, 1.0, 0.01),
}
SHAPE_KNOBS = ("twirl", "spin", "blooms", "bloom", "bloom_size", "rounds", "warp", "contrast")
SWITCHES = ("smooth", "logical_px", "parallax")
SLIDER_STEPS = 1000
# Which colour each button edits: (GroundHue field, index)
COLOURS = (
    ("colour_1", "swirl", 0),
    ("colour_2", "swirl", 1),
    ("colour_3", "swirl", 2),
    ("aura centre", "aura", 0),
    ("aura middle", "aura", 1),
    ("aura edge", "aura", 2),
)

# What reset goes back to
_PARAMS_AT_START = dict(swirl.PARAMS)
_HUES_AT_START = {
    hue_id: (tuple(map(QColor, hue.swirl)), tuple(map(QColor, hue.aura)))
    for hue_id, hue in GROUND_HUES.items()
}


def _changed():
    swirl.tuning.changed.emit()


def _set_param(name, value):
    if swirl.PARAMS[name] == value:
        return
    swirl.PARAMS[name] = value
    _changed()


def _hue():
    return GROUND_HUES[swirl.tuning.hue_id]


def _ink(colour):
    return "#000" if colour.lightnessF() > 0.55 else "#fff"


def _python(hue_id):
    """The edited preset and PARAMS as source"""
    hue = GROUND_HUES[hue_id]

    def colours(values):
        return ", ".join(f'QColor("{c.name()}")' for c in values)

    lines = [
        f'    "{hue_id}": GroundHue(',
        f"        swirl=({colours(hue.swirl)}),",
        f"        aura=({colours(hue.aura)}),",
        "    ),",
        "",
        "PARAMS = {",
    ]
    for name, value in swirl.PARAMS.items():
        shown = round(value, 3) if isinstance(value, float) else value
        lines.append(f'    "{name}": {shown!r},')
    lines.append("}")
    return "\n".join(lines) + "\n"


class _Knob(QWidget):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name
        low, high, step = RANGES[name]
        self.is_int = isinstance(step, int)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimumWidth(220)
        if self.is_int:
            self.box = QSpinBox()
            self.box.setRange(low, high)
            self.slider.setRange(low, high)
        else:
            self.box = QDoubleSpinBox()
            self.box.setRange(low, high)
            self.box.setSingleStep(step)
            self.box.setDecimals(3)
            self.slider.setRange(0, SLIDER_STEPS)
        self._low, self._high = low, high
        row.addWidget(self.slider, 1)
        row.addWidget(self.box)
        self.slider.valueChanged.connect(self._from_slider)
        self.box.valueChanged.connect(self._from_box)
        self.load()

    def load(self):
        value = swirl.PARAMS[self.name]
        self.box.blockSignals(True)
        self.slider.blockSignals(True)
        self.box.setValue(value)
        self.slider.setValue(value if self.is_int else self._to_slider(value))
        self.box.blockSignals(False)
        self.slider.blockSignals(False)

    def _to_slider(self, value):
        return round((value - self._low) / (self._high - self._low) * SLIDER_STEPS)

    def _from_slider(self, position):
        value = (
            position
            if self.is_int
            else self._low + position / SLIDER_STEPS * (self._high - self._low)
        )
        self.box.setValue(value)

    def _from_box(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(value if self.is_int else self._to_slider(value))
        self.slider.blockSignals(False)
        _set_param(self.name, value)


class _ColourButton(QPushButton):
    """One of the edited preset's six colours"""

    def __init__(self, field, index, on_change, parent=None):
        super().__init__(parent)
        self.field = field
        self.index = index
        self.on_change = on_change
        self.clicked.connect(self._pick)

    def colour(self):
        return getattr(_hue(), self.field)[self.index]

    def load(self):
        colour = self.colour()
        self.setText(colour.name())
        self.setStyleSheet(f"background: {colour.name()}; color: {_ink(colour)};")

    def _pick(self):
        before = QColor(self.colour())
        dialog = QColorDialog(before, self)
        dialog.currentColorChanged.connect(self._set)
        if not dialog.exec():
            self._set(before)

    def _set(self, colour):
        values = list(getattr(_hue(), self.field))
        values[self.index] = QColor(colour)
        setattr(_hue(), self.field, tuple(values))
        self.load()
        self.on_change()


class _AuraPreview(QWidget):
    """The edited preset's Aura, as the canvas draws it at 1x zoom, centred"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 180)

    def paintEvent(self, event):
        painter = QPainter(self)
        # The canvas's radius is 800 scene px; keep the falloff's shape at this size
        radius = 800 * self.width() / 1280
        gradient = QRadialGradient(QPointF(self.width() / 2, self.height() / 2), radius)
        gradient.setStops(_hue().aura_stops())
        painter.fillRect(self.rect(), gradient)
        painter.end()


class SwirlDock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("ground tuning")
        if swirl.tuning.hue_id is None:
            swirl.tuning.hue_id = ground_hue_id()
        form = QFormLayout(self)

        self.hue_combo = QComboBox()
        self.hue_combo.addItems(GROUND_HUES)
        self.hue_combo.setCurrentText(swirl.tuning.hue_id)
        self.hue_combo.currentTextChanged.connect(self._pick_hue)
        form.addRow("hue", self.hue_combo)
        self.colours = []
        for label, field, index in COLOURS:
            button = _ColourButton(field, index, self._colour_changed)
            self.colours.append(button)
            form.addRow(label, button)
        self.preview = _AuraPreview()
        form.addRow("aura", self.preview)

        self.knobs = []
        for name in (*SHAPE_KNOBS, "speed", "pixel", "every"):
            knob = _Knob(name)
            self.knobs.append(knob)
            form.addRow(name, knob)
        self.switches = {}
        for name in SWITCHES:
            check = QCheckBox()
            check.toggled.connect(lambda on, name=name: _set_param(name, on))
            self.switches[name] = check
            form.addRow(name, check)
        for name in ("parallax_pan", "parallax_zoom"):
            knob = _Knob(name)
            self.knobs.append(knob)
            form.addRow(name, knob)

        buttons = QHBoxLayout()
        reset = QPushButton("reset")
        reset.clicked.connect(self._reset)
        buttons.addWidget(reset)
        copy = QPushButton("copy")
        copy.clicked.connect(self._copy)
        buttons.addWidget(copy)
        form.addRow("", buttons)

        self.readout = QLabel()
        self.readout.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("", self.readout)
        self._load()

        self._timer = QTimer(self, interval=250)
        self._timer.timeout.connect(self._show_timings)
        self._timer.start()

    def _load(self):
        for knob in self.knobs:
            knob.load()
        for button in self.colours:
            button.load()
        for name, check in self.switches.items():
            check.blockSignals(True)
            check.setChecked(bool(swirl.PARAMS[name]))
            check.blockSignals(False)
        self.preview.update()

    def _pick_hue(self, hue_id):
        swirl.tuning.hue_id = hue_id
        self._load()
        _changed()

    def _colour_changed(self):
        self.preview.update()
        _changed()

    def _reset(self):
        swirl.PARAMS.clear()
        swirl.PARAMS.update(_PARAMS_AT_START)
        for hue_id, (swirl_colours, aura) in _HUES_AT_START.items():
            GROUND_HUES[hue_id].swirl = tuple(map(QColor, swirl_colours))
            GROUND_HUES[hue_id].aura = tuple(map(QColor, aura))
        self._load()
        _changed()

    def _copy(self):
        QGuiApplication.clipboard().setText(_python(swirl.tuning.hue_id))

    def _show_timings(self):
        field = swirl._field
        size = field.size if field is not None else None
        shown = f"{size.width()}x{size.height()}" if size is not None and size.isValid() else "-"
        last = field.last_ms if field is not None else None
        ms = f"{last:.2f}" if last is not None else "-"
        window = self.parentWidget()
        dpr = window.devicePixelRatioF() if window is not None else self.devicePixelRatioF()
        self.readout.setText(
            f"dpr {dpr:g}  divisor {swirl.divisor(dpr):g}\nfield {shown}  render ms {ms}"
        )

    def showEvent(self, event):
        super().showEvent(event)
        _changed()

    def hideEvent(self, event):
        super().hideEvent(event)
        # The canvas goes back to the stored preset
        _changed()
