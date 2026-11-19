"""A panel to choose the canvas's own background, or on a tab that keeps none its kind's."""

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

from tarot_canvas.models.ground import (
    EVERY_CANVAS,
    Ground,
    drawn,
    follows,
    kind_ground,
    set_kind_ground,
)
from tarot_canvas.settings import get_settings
from tarot_canvas.ui import commands, units
from tarot_canvas.ui.canvas.canvas_panel import CanvasPanel
from tarot_canvas.ui.strings import CANVAS, PREFERENCES
from tarot_canvas.ui.windows.background_form import BackgroundForm, canvas_aspect, radio_indent

COMMAND = "window.canvas_background"

# Room for the image strip to show a few tiles, and for its three buttons in a row
PANEL_WIDTH = 20 * units.GRID_UNIT


class BackgroundPanel(CanvasPanel):
    """Follow the default, or give the tab a ground of its own.

    A tab that keeps no ground (the designer) edits its kind's instead: the same two
    choices as the kind's in Preferences, kept in the settings by Apply.
    """

    # The settings were written, so every canvas following them should redraw
    default_changed = pyqtSignal()

    def __init__(self, tab, parent):
        super().__init__(commands.by_id(COMMAND).text, tab.view, parent)
        self.tab = tab
        self.opened_on = tab.ground
        self.kind = kind = tab.GROUND_KIND
        self.edits_kind = not tab.OWN_GROUND

        if self.edits_kind:
            follow_text = PREFERENCES["background_scope_follow"]
            own_text = PREFERENCES["background_scope_own"]
            own_ground = kind_ground(kind)
        else:
            follow_text = CANVAS[f"background_follow_{follows(kind)}"]
            own_text = CANVAS["background_own"]
            own_ground = tab.ground

        self.follow = QRadioButton(follow_text)
        self.own = QRadioButton(own_text)
        self.choice = QButtonGroup(self)
        self.choice.addButton(self.follow)
        self.choice.addButton(self.own)
        self.form = BackgroundForm(canvas_aspect(tab), compact=True)
        self.form.reload()
        self.form.set_ground(own_ground or drawn(None, kind))
        self.form.setRowsEnabled(own_ground is not None)

        group = QVBoxLayout()
        group.setSpacing(units.SMALL_SPACING)
        group.addWidget(self.follow)
        group.addWidget(self.own)
        rows = QHBoxLayout()
        rows.setContentsMargins(radio_indent(self.style()), 0, 0, 0)
        rows.addWidget(self.form)
        group.addLayout(rows)
        (self.follow if own_ground is None else self.own).setChecked(True)
        group.addSpacing(units.LARGE_SPACING)

        self.use_for_button = QPushButton(
            QIcon.fromTheme("document-save-as-template"), CANVAS["background_use_for"]
        )
        self.use_for_button.setAutoDefault(False)
        self.use_for_menu = QMenu(self.use_for_button)
        # Where the panel edits the kind's, the kind is the Custom radio, not an entry
        for level in (EVERY_CANVAS,) if self.edits_kind else (EVERY_CANVAS, kind):
            action = self.use_for_menu.addAction(CANVAS[f"background_use_for_{level}"])
            action.setData(level)
            action.triggered.connect(lambda _checked, level=level: self.use_for(level))
        self.use_for_button.setMenu(self.use_for_menu)
        self.buttons.addButton(self.use_for_button, QDialogButtonBox.ButtonRole.ResetRole)

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
        ground = self.chosen()
        if self.edits_kind and ground is None:
            # Following, the kind draws every canvas's, which the tab's own None wouldn't show
            ground = Ground.from_settings()
        # On a tab that keeps none, its own is only the preview, put back by Apply or Cancel
        self.tab.ground = ground
        self.tab.apply_ground()

    def restore(self):
        self.tab.ground = self.opened_on
        self.tab.apply_ground()

    def apply(self):
        if self.edits_kind and not self.finished:
            set_kind_ground(self.kind, self.chosen())
            self.restore()
            super().apply()
            self.default_changed.emit()
            return
        super().apply()

    def use_for(self, level):
        ground = self.form.ground()
        settings = get_settings()
        if level == EVERY_CANVAS:
            ground.to_settings(settings)
        else:
            set_kind_ground(level, ground, settings)
        self.follow.setChecked(True)
        self.apply()
        # Apply on the kind's says so itself
        if not self.edits_kind:
            self.default_changed.emit()
