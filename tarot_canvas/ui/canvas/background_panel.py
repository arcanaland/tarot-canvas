"""A panel to choose the canvas's own background."""

from PyQt6.QtCore import QRectF, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialogButtonBox,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from tarot_canvas.models.ground import EVERY_CANVAS, drawn, follows, set_kind_ground
from tarot_canvas.settings import get_settings
from tarot_canvas.ui import commands, units
from tarot_canvas.ui.canvas.canvas_panel import CanvasPanel
from tarot_canvas.ui.strings import CANVAS
from tarot_canvas.ui.windows.background_form import BackgroundForm, canvas_aspect, radio_indent

COMMAND = "window.canvas_background"

# Room for the image strip to show a few tiles, and for its three buttons in a row
PANEL_WIDTH = 20 * units.GRID_UNIT


class BackgroundPanel(CanvasPanel):
    """Follow the default, or give the tab a ground of its own"""

    # Use for wrote the settings, so every canvas following them should redraw
    default_changed = pyqtSignal()

    def __init__(self, tab, parent):
        super().__init__(commands.by_id(COMMAND).text, tab.view, parent)
        self.tab = tab
        self.opened_on = tab.ground
        kind = tab.GROUND_KIND

        self.follow = QRadioButton(CANVAS[f"background_follow_{follows(kind)}"])
        self.choice = QButtonGroup(self)
        self.choice.addButton(self.follow)
        group = QVBoxLayout()
        group.setSpacing(units.SMALL_SPACING)
        group.addWidget(self.follow)

        self.own = self.form = None
        if tab.OWN_GROUND:
            self.own = QRadioButton(CANVAS["background_own"])
            self.choice.addButton(self.own)
            self.form = BackgroundForm(canvas_aspect(tab), compact=True)
            self.form.reload()
            self.form.set_ground(tab.ground or drawn(None, kind))
            self.form.setRowsEnabled(tab.ground is not None)
            group.addWidget(self.own)
            rows = QHBoxLayout()
            rows.setContentsMargins(radio_indent(self.style()), 0, 0, 0)
            rows.addWidget(self.form)
            group.addLayout(rows)
        (self.follow if tab.ground is None else self.own).setChecked(True)
        group.addSpacing(units.LARGE_SPACING)

        self.use_for_button = QPushButton(
            QIcon.fromTheme("document-save-as-template"), CANVAS["background_use_for"]
        )
        self.use_for_button.setAutoDefault(False)
        self.use_for_menu = QMenu(self.use_for_button)
        for level in (EVERY_CANVAS, kind):
            action = self.use_for_menu.addAction(CANVAS[f"background_use_for_{level}"])
            action.setData(level)
            action.triggered.connect(lambda _checked, level=level: self.use_for(level))
        self.use_for_button.setMenu(self.use_for_menu)
        self.buttons.addButton(self.use_for_button, QDialogButtonBox.ButtonRole.ResetRole)

        self.lay_out(group)
        self.setMinimumWidth(PANEL_WIDTH)

        if self.form is not None:
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
        return self.form.ground() if self.own is not None and self.own.isChecked() else None

    def shown(self):
        """The ground Use for writes: the form's, or without one what the canvas draws"""
        return self.form.ground() if self.form is not None else self.tab.drawn_ground()

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

    def use_for(self, level):
        ground = self.shown()
        settings = get_settings()
        if level == EVERY_CANVAS:
            ground.to_settings(settings)
        else:
            set_kind_ground(level, ground, settings)
        self.follow.setChecked(True)
        self.apply()
        self.default_changed.emit()
