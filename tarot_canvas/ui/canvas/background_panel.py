"""A panel to choose the canvas's own background."""

from PyQt6.QtCore import QRectF, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialogButtonBox,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QStyle,
    QVBoxLayout,
)

from tarot_canvas.models.ground import Ground
from tarot_canvas.settings import get_settings
from tarot_canvas.ui import commands
from tarot_canvas.ui.canvas.canvas_panel import CanvasPanel
from tarot_canvas.ui.library import units
from tarot_canvas.ui.strings import CANVAS
from tarot_canvas.ui.windows.background_form import BackgroundForm, canvas_aspect

COMMAND = "window.canvas_background"

# Room for the image strip to show a few tiles, and for its three buttons in a row
PANEL_WIDTH = 20 * units.GRID_UNIT


def radio_indent(style):
    """Where a radio button's text starts, so what belongs to it can line up under it"""
    return style.pixelMetric(QStyle.PixelMetric.PM_ExclusiveIndicatorWidth) + style.pixelMetric(
        QStyle.PixelMetric.PM_RadioButtonLabelSpacing
    )


class BackgroundPanel(CanvasPanel):
    """Follow the default, or give the tab a ground of its own"""

    # Use as Default wrote the settings, so every canvas following them should redraw
    default_changed = pyqtSignal()

    def __init__(self, tab, parent):
        super().__init__(commands.by_id(COMMAND).text, tab.view, parent)
        self.tab = tab
        self.opened_on = tab.ground

        self.follow = QRadioButton(CANVAS["background_follow"])
        self.own = QRadioButton(CANVAS["background_own"])
        self.choice = QButtonGroup(self)
        self.choice.addButton(self.follow)
        self.choice.addButton(self.own)
        (self.follow if tab.ground is None else self.own).setChecked(True)
        self.form = BackgroundForm(canvas_aspect(tab), compact=True)
        self.form.reload()
        self.form.set_ground(tab.ground or Ground.from_settings(get_settings()))
        self.form.setRowsEnabled(tab.ground is not None)

        group = QVBoxLayout()
        group.setSpacing(units.SMALL_SPACING)
        group.addWidget(self.follow)
        group.addWidget(self.own)
        rows = QHBoxLayout()
        rows.setContentsMargins(radio_indent(self.style()), 0, 0, 0)
        rows.addWidget(self.form)
        group.addLayout(rows)
        group.addSpacing(units.LARGE_SPACING)

        self.default_button = QPushButton(
            QIcon.fromTheme("document-save-as-template"), CANVAS["background_use_as_default"]
        )
        self.default_button.setAutoDefault(False)
        self.default_button.clicked.connect(self.use_as_default)
        self.buttons.addButton(self.default_button, QDialogButtonBox.ButtonRole.ResetRole)

        self.lay_out(group)
        self.setMinimumWidth(PANEL_WIDTH)

        self.choice.buttonToggled.connect(self._on_choice_toggled)
        self.form.changed.connect(self.preview)
        # Its rows come and go with the type
        self.form.changed.connect(self.refit)

    def covered_rect(self):
        """Every card on the tab"""
        rect = QRectF()
        for card in self.tab.cards():
            rect = rect.united(card.sceneBoundingRect())
        return rect

    def chosen(self):
        """The option the user selected"""
        return self.form.ground() if self.own.isChecked() else None

    def _on_choice_toggled(self, _button, checked):
        if checked:
            self.form.setRowsEnabled(self.own.isChecked())
            self.preview()

    def preview(self):
        if self.finished:
            return
        self.tab.ground = self.chosen()
        self.tab.apply_ground()

    def restore(self):
        self.tab.ground = self.opened_on
        self.tab.apply_ground()

    def use_as_default(self):
        self.form.ground().to_settings(get_settings())
        self.follow.setChecked(True)
        self.apply()
        self.default_changed.emit()
