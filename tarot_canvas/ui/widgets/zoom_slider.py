"""A slider between zoom-out and zoom-in buttons"""

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QHBoxLayout, QSlider, QToolButton, QWidget

from tarot_canvas.ui.windows.preferences_text import PREFERENCES_TEXT

SLIDER_WIDTH = 96


def _plain(label):
    return label.replace("&", "")


class ZoomSlider(QWidget):
    """One stop per key (smallest first)"""

    key_changed = pyqtSignal(str)

    def __init__(self, keys, tooltip, default, parent=None):
        super().__init__(parent)
        self._keys = list(keys)
        self._default = default

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.out_button = self._button("zoom-out", _plain(PREFERENCES_TEXT["zoom_out"]))
        self.out_button.clicked.connect(self.step_out)
        row.addWidget(self.out_button)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, len(self._keys) - 1)
        self.slider.setPageStep(1)
        self.slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self.slider.setFixedWidth(SLIDER_WIDTH)
        self.slider.setToolTip(tooltip)
        self.slider.setAccessibleName(tooltip)
        self.slider.valueChanged.connect(self._on_value_changed)
        row.addWidget(self.slider)

        self.in_button = self._button("zoom-in", _plain(PREFERENCES_TEXT["zoom_in"]))
        self.in_button.clicked.connect(self.step_in)
        row.addWidget(self.in_button)

        self._update_buttons()

    @staticmethod
    def _button(icon, text):
        button = QToolButton()
        button.setIcon(QIcon.fromTheme(icon))
        button.setToolTip(text)
        button.setAccessibleName(text)
        button.setAutoRaise(True)
        return button

    def key(self):
        return self._keys[self.slider.value()]

    def set_key(self, key):
        """Move to key without emitting key_changed"""
        if key not in self._keys:
            return
        self.slider.blockSignals(True)
        self.slider.setValue(self._keys.index(key))
        self.slider.blockSignals(False)
        self._update_buttons()

    def can_step_in(self):
        return self.slider.value() < self.slider.maximum()

    def can_step_out(self):
        return self.slider.value() > self.slider.minimum()

    def step_in(self):
        self.slider.setValue(self.slider.value() + 1)

    def step_out(self):
        self.slider.setValue(self.slider.value() - 1)

    def can_zoom(self, how):
        return {
            "in": self.can_step_in(),
            "out": self.can_step_out(),
            "reset": self.key() != self._default,
        }[how]

    def zoom(self, how):
        if how == "in":
            self.step_in()
        elif how == "out":
            self.step_out()
        elif self._default in self._keys:
            self.slider.setValue(self._keys.index(self._default))

    def zoom_on_ctrl_wheel(self, widget):
        """Ctrl+wheel over widget steps the slider instead of scrolling"""
        widget.installEventFilter(_CtrlWheel(self, widget))

    def _on_value_changed(self, _value):
        self._update_buttons()
        self.key_changed.emit(self.key())

    def _update_buttons(self):
        self.out_button.setEnabled(self.can_step_out())
        self.in_button.setEnabled(self.can_step_in())


class _CtrlWheel(QObject):
    def __init__(self, zoom, parent):
        super().__init__(parent)
        self._zoom = zoom

    def eventFilter(self, _watched, event):
        if (
            event.type() != QEvent.Type.Wheel
            or not event.modifiers() & Qt.KeyboardModifier.ControlModifier
            # Hidden, it isn't this page's zoom
            or not self._zoom.isVisible()
        ):
            return False
        delta = event.angleDelta().y()
        how = "in" if delta > 0 else "out"
        if delta and self._zoom.can_zoom(how):
            self._zoom.zoom(how)
        return True
