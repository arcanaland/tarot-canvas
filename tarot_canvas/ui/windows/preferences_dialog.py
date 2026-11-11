import sys

from PyQt6.QtCore import QLocale, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.ground import Ground
from tarot_canvas.settings import (
    CANVAS_GUIDES_DEFAULT,
    CANVAS_GUIDES_KEY,
    CANVAS_TAB_MINIMAP_DEFAULT,
    CANVAS_TAB_MINIMAP_KEY,
    HARDWARE_ACCELERATION_DEFAULT,
    HARDWARE_ACCELERATION_KEY,
    MOTION_LEVEL_DEFAULT,
    MOTION_LEVEL_KEY,
    PREFERENCES_GEOMETRY_KEY,
    PREFERENCES_PAGE_KEY,
    READING_TEXT_SCALE_DEFAULT,
    READING_TEXT_SCALE_STEPS,
    SHOW_AVAILABLE_DECKS_DEFAULT,
    SHOW_AVAILABLE_DECKS_KEY,
    SHOW_WELCOME_DEFAULT,
    get_motion_level,
    get_settings,
    get_show_welcome,
    set_show_welcome,
)
from tarot_canvas.ui import typography, units
from tarot_canvas.ui.canvas.gl_marker import clear_marker
from tarot_canvas.ui.icons import LIBRARY_ICON
from tarot_canvas.ui.strings import MAIN_WINDOW, PREFERENCES
from tarot_canvas.ui.widgets.pane_text import pane_form
from tarot_canvas.ui.widgets.places_sidebar import PlacesSidebar
from tarot_canvas.ui.windows.background_form import (
    BackgroundForm,
    canvas_aspect,
    keyed_combo,
    select_data,
)
from tarot_canvas.ui.windows.shortcuts_page import ShortcutsPage
from tarot_canvas.utils.theme_manager import ThemeManager, ThemeType

THEME_LABELS = (
    (ThemeType.SYSTEM.value, PREFERENCES["theme_system"]),
    (ThemeType.LIGHT.value, PREFERENCES["theme_light"]),
    (ThemeType.DARK.value, PREFERENCES["theme_dark"]),
)

MOTION_LEVEL_LABELS = (
    ("Off", PREFERENCES["motion_off"]),
    ("Reactive", PREFERENCES["motion_reactive"]),
    ("Full", PREFERENCES["motion_full"]),
)


def percent_labels(steps):
    """using locale"""
    locale = QLocale()
    return tuple((step, locale.toString(step) + locale.percent()) for step in steps)


class PreferencesDialog(QDialog):
    settings_changed = pyqtSignal()

    DEFAULT_SIZE = QSize(40 * units.GRID_UNIT, 26 * units.GRID_UNIT)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(PREFERENCES["title"])
        self.stored_state = None
        self.hardware_acceleration_check = None

        self.page_list = PlacesSidebar(
            [
                (QIcon.fromTheme(icon_name), PREFERENCES[key], key)
                for key, icon_name, _build in self.pages()
            ],
            filled=True,
        )
        self.page_stack = QStackedWidget()
        for _key, _icon_name, build in self.pages():
            self.page_stack.addWidget(build())

        # The selected page's name header
        self.page_title = typography.apply(QLabel(), typography.Role.HEADING_1)
        self.page_title.setTextFormat(Qt.TextFormat.PlainText)
        header = QWidget()
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(
            units.LARGE_SPACING, units.LARGE_SPACING, units.LARGE_SPACING, units.LARGE_SPACING
        )
        header_row.addWidget(self.page_title)

        self.page_list.currentRowChanged.connect(self.show_page)
        self.page_list.setCurrentRow(self.remembered_page_row())

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.apply_button = self.button_box.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_button.clicked.connect(self.apply_settings)
        self.button_box.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self.restore_defaults
        )

        body = QVBoxLayout()
        body.setContentsMargins(units.LARGE_SPACING, 0, units.LARGE_SPACING, units.LARGE_SPACING)
        # Its own, or it takes content_column's none
        body.setSpacing(units.LARGE_SPACING)
        body.addWidget(self.page_stack, 1)
        body.addWidget(self.button_box)

        content_column = QVBoxLayout()
        content_column.setContentsMargins(0, 0, 0, 0)
        content_column.setSpacing(0)
        content_column.addWidget(header)
        content_column.addLayout(body, 1)

        # [sidebar | seam | title over (page, buttons)]
        seam = QFrame()
        seam.setFrameShape(QFrame.Shape.VLine)
        seam.setFrameShadow(QFrame.Shadow.Sunken)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.page_list)
        layout.addWidget(seam)
        layout.addLayout(content_column, 1)

        self.page_list.center_first_row_on(header.sizeHint().height())

        self.resize(self.sizeHint().expandedTo(self.DEFAULT_SIZE))
        geometry = get_settings().value(PREFERENCES_GEOMETRY_KEY)
        if geometry is not None:
            self.restoreGeometry(geometry)

        self.load_settings()

        for combo in (self.theme_combo, self.text_size_combo, self.motion_combo):
            combo.currentIndexChanged.connect(self.update_apply_button)
        self.background_form.changed.connect(self.update_apply_button)
        self.show_available_decks_check.toggled.connect(self.update_apply_button)
        self.show_welcome_check.toggled.connect(self.update_apply_button)
        self.canvas_tab_minimap_check.toggled.connect(self.update_apply_button)
        self.canvas_guides_check.toggled.connect(self.update_apply_button)
        self.shortcuts_page.changed.connect(self.update_apply_button)
        if self.hardware_acceleration_check:
            self.hardware_acceleration_check.toggled.connect(self.update_apply_button)

    def pages(self):
        """The sidebar's pages in order"""
        pages = [
            ("appearance", "games-config-theme", self.build_appearance_page),
            ("canvas", "draw-rectangle", self.build_canvas_page),
            ("background", "folder-image-symbolic", self.build_background_page),
            ("library", LIBRARY_ICON, self.build_library_page),
            ("shortcuts", "configure-shortcuts", self.build_shortcuts_page),
        ]
        if sys.platform == "linux":
            pages.append(("advanced", "preferences-system", self.build_advanced_page))
        return pages

    def page_keys(self):
        return [key for key, _icon_name, _build in self.pages()]

    def remembered_page_row(self):
        """The row of the page last shown, else the first"""
        key = get_settings().value(PREFERENCES_PAGE_KEY, "", type=str)
        keys = self.page_keys()
        return keys.index(key) if key in keys else 0

    def show_page(self, row):
        self.page_stack.setCurrentIndex(row)
        self.page_title.setText(self.page_list.item(row).text())

    def build_appearance_page(self):
        page = QWidget()
        form = pane_form()
        self.theme_combo = keyed_combo(THEME_LABELS)
        form.addRow(PREFERENCES["theme"], self.theme_combo)
        self.text_size_combo = keyed_combo(percent_labels(READING_TEXT_SCALE_STEPS))
        form.addRow(PREFERENCES["text_size"], self.text_size_combo)
        self.show_welcome_check = QCheckBox(MAIN_WINDOW["welcome_show_at_startup"])
        form.addRow(PREFERENCES["startup_label"], self.show_welcome_check)
        page.setLayout(form)
        return page

    def build_canvas_page(self):
        page = QWidget()
        form = pane_form()

        self.motion_combo = keyed_combo(MOTION_LEVEL_LABELS)
        form.addRow(PREFERENCES["canvas_motion"], self.motion_combo)

        self.canvas_tab_minimap_check = QCheckBox(PREFERENCES["canvas_tab_minimap"])
        form.addRow(PREFERENCES["canvas_tabs"], self.canvas_tab_minimap_check)

        self.canvas_guides_check = QCheckBox(PREFERENCES["canvas_guides_snap"])
        form.addRow(PREFERENCES["canvas_guides"], self.canvas_guides_check)

        page.setLayout(form)
        return page

    def build_background_page(self):
        """The default ground, which every canvas without its own draws"""
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel(PREFERENCES["background_default_note"])
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setWordWrap(True)
        layout.addWidget(note)
        self.background_form = BackgroundForm(canvas_aspect(self.parentWidget()))
        layout.addWidget(self.background_form, 1)
        return page

    def build_library_page(self):
        page = QWidget()
        form = pane_form()
        # Ghost tiles for catalog decks not installed yet
        self.show_available_decks_check = QCheckBox(PREFERENCES["show_available_decks"])
        form.addRow(PREFERENCES["library_label"], self.show_available_decks_check)
        page.setLayout(form)
        return page

    def build_advanced_page(self):
        page = QWidget()
        form = pane_form()
        self.hardware_acceleration_check = QCheckBox(PREFERENCES["hardware_acceleration"])
        form.addRow(self.hardware_acceleration_check)
        note = typography.apply(
            QLabel(PREFERENCES["hardware_acceleration_note"]), typography.Role.SMALL
        )
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setWordWrap(True)
        form.addRow(note)
        page.setLayout(form)
        return page

    def build_shortcuts_page(self):
        self.shortcuts_page = ShortcutsPage()
        return self.shortcuts_page

    def form_state(self):
        """What the form says, in the terms it is stored in"""
        return (
            self.theme_combo.currentData(),
            self.text_size_combo.currentData(),
            self.background_form.ground(),
            self.background_form.pending_removals(),
            self.motion_combo.currentData(),
            self.canvas_tab_minimap_check.isChecked(),
            self.canvas_guides_check.isChecked(),
            self.show_available_decks_check.isChecked(),
            self.show_welcome_check.isChecked(),
            self.hardware_acceleration_check.isChecked()
            if self.hardware_acceleration_check
            else None,
            self.shortcuts_page.state(),
        )

    def update_apply_button(self):
        """Apply is offered only while the form differs from what is stored"""
        self.apply_button.setEnabled(
            self.stored_state is not None and self.form_state() != self.stored_state
        )

    def show_state(
        self,
        theme,
        text_size,
        ground,
        motion,
        tab_minimap,
        guides,
        show_available,
        show_welcome,
        hardware_acceleration,
    ):
        select_data(self.theme_combo, theme)
        select_data(self.text_size_combo, text_size)
        self.background_form.set_ground(ground)
        select_data(self.motion_combo, motion)
        self.canvas_tab_minimap_check.setChecked(tab_minimap)
        self.canvas_guides_check.setChecked(guides)
        self.show_available_decks_check.setChecked(show_available)
        self.show_welcome_check.setChecked(show_welcome)
        if self.hardware_acceleration_check:
            self.hardware_acceleration_check.setChecked(hardware_acceleration)
        self.update_apply_button()

    def load_settings(self):
        settings = get_settings()
        self.background_form.reload()
        self.show_state(
            ThemeManager.get_instance().get_current_theme().value,
            typography.reading_scale(),
            Ground.from_settings(settings),
            get_motion_level(settings),
            bool(settings.value(CANVAS_TAB_MINIMAP_KEY, CANVAS_TAB_MINIMAP_DEFAULT, type=bool)),
            bool(settings.value(CANVAS_GUIDES_KEY, CANVAS_GUIDES_DEFAULT, type=bool)),
            bool(settings.value(SHOW_AVAILABLE_DECKS_KEY, SHOW_AVAILABLE_DECKS_DEFAULT, type=bool)),
            get_show_welcome(settings),
            self.stored_hardware_acceleration(settings),
        )
        self.shortcuts_page.load()
        self.stored_state = self.form_state()
        self.update_apply_button()

    @staticmethod
    def stored_hardware_acceleration(settings):
        return bool(
            settings.value(HARDWARE_ACCELERATION_KEY, HARDWARE_ACCELERATION_DEFAULT, type=bool)
        )

    def restore_defaults(self):
        self.show_state(
            ThemeType.SYSTEM.value,
            READING_TEXT_SCALE_DEFAULT,
            Ground(),
            MOTION_LEVEL_DEFAULT,
            CANVAS_TAB_MINIMAP_DEFAULT,
            CANVAS_GUIDES_DEFAULT,
            SHOW_AVAILABLE_DECKS_DEFAULT,
            SHOW_WELCOME_DEFAULT,
            HARDWARE_ACCELERATION_DEFAULT,
        )
        self.shortcuts_page.reset()

    def apply_settings(self):
        settings = get_settings()
        self.background_form.ground().to_settings(settings)
        settings.setValue(MOTION_LEVEL_KEY, self.motion_combo.currentData())
        self.background_form.commit_removals()
        settings.setValue(CANVAS_TAB_MINIMAP_KEY, self.canvas_tab_minimap_check.isChecked())
        settings.setValue(CANVAS_GUIDES_KEY, self.canvas_guides_check.isChecked())
        settings.setValue(SHOW_AVAILABLE_DECKS_KEY, self.show_available_decks_check.isChecked())
        set_show_welcome(self.show_welcome_check.isChecked(), settings)
        if self.hardware_acceleration_check:
            enabled = self.hardware_acceleration_check.isChecked()
            if enabled and not self.stored_hardware_acceleration(settings):
                clear_marker()
            settings.setValue(HARDWARE_ACCELERATION_KEY, enabled)

        ThemeManager.get_instance().set_theme(ThemeType(self.theme_combo.currentData()))
        typography.set_reading_scale(self.text_size_combo.currentData())
        self.shortcuts_page.apply()

        self.stored_state = self.form_state()
        self.update_apply_button()
        self.settings_changed.emit()

    def accept(self):
        self.apply_settings()
        super().accept()

    def done(self, result):
        settings = get_settings()
        settings.setValue(PREFERENCES_GEOMETRY_KEY, self.saveGeometry())
        settings.setValue(PREFERENCES_PAGE_KEY, self.page_keys()[self.page_list.currentRow()])
        super().done(result)
