import sys

from PyQt6.QtCore import QLocale, QRectF, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QPainter,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models import backgrounds
from tarot_canvas.settings import (
    BACKGROUND_COLOR_DEFAULT,
    BACKGROUND_COLOR_KEY,
    BACKGROUND_FILL_DEFAULT,
    BACKGROUND_FILL_KEY,
    BACKGROUND_IMAGE_DEFAULT,
    BACKGROUND_IMAGE_KEY,
    BACKGROUND_POSITIONING_DEFAULT,
    BACKGROUND_POSITIONING_KEY,
    BACKGROUND_STYLE_DEFAULT,
    BACKGROUND_STYLE_KEY,
    CANVAS_GUIDES_DEFAULT,
    CANVAS_GUIDES_KEY,
    CANVAS_TAB_MINIMAP_DEFAULT,
    CANVAS_TAB_MINIMAP_KEY,
    CHECKERBOARD_COLOR_DEFAULT,
    CHECKERBOARD_COLOR_KEY,
    GROUND_HUE_KEY,
    HARDWARE_ACCELERATION_DEFAULT,
    HARDWARE_ACCELERATION_KEY,
    MOTION_LEVEL_DEFAULT,
    MOTION_LEVEL_KEY,
    PREFERENCES_GEOMETRY_KEY,
    READING_TEXT_SCALE_DEFAULT,
    READING_TEXT_SCALE_STEPS,
    SHOW_AVAILABLE_DECKS_DEFAULT,
    SHOW_AVAILABLE_DECKS_KEY,
    get_background_positioning,
    get_background_style,
    get_motion_level,
    get_settings,
)
from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas.gl_marker import clear_marker
from tarot_canvas.ui.canvas.ground import GROUND_HUE_DEFAULT, GROUND_HUES, ground_hue_id
from tarot_canvas.ui.icons import LIBRARY_ICON
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.pane_text import pane_form
from tarot_canvas.ui.strings import PREFERENCES
from tarot_canvas.ui.widgets.places_sidebar import PlacesSidebar
from tarot_canvas.ui.windows.background_grid import BackgroundGrid
from tarot_canvas.ui.windows.shortcuts_page import ShortcutsPage
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.theme_manager import ThemeManager, ThemeType

THEME_LABELS = (
    (ThemeType.SYSTEM.value, PREFERENCES["theme_system"]),
    (ThemeType.LIGHT.value, PREFERENCES["theme_light"]),
    (ThemeType.DARK.value, PREFERENCES["theme_dark"]),
)

BACKGROUND_STYLE_LABELS = (
    ("gradient", PREFERENCES["background_gradient"]),
    ("swirl", PREFERENCES["background_swirl"]),
    ("image", PREFERENCES["background_image"]),
    ("checkerboard", PREFERENCES["background_checkerboard"]),
    ("solid", PREFERENCES["background_solid"]),
)

POSITIONING_LABELS = (
    ("crop", PREFERENCES["positioning_crop"]),
    ("stretch", PREFERENCES["positioning_stretch"]),
    ("fit", PREFERENCES["positioning_fit"]),
    ("center", PREFERENCES["positioning_center"]),
    ("tile", PREFERENCES["positioning_tile"]),
)
# The types drawn in a GroundHue, which show the hue row
HUED_STYLES = ("gradient", "swirl")

# The positionings that can leave the canvas uncovered, where the fill shows
FILLED_POSITIONINGS = ("fit", "center")

MOTION_LEVEL_LABELS = (
    ("Off", PREFERENCES["motion_off"]),
    ("Reactive", PREFERENCES["motion_reactive"]),
    ("Full", PREFERENCES["motion_full"]),
)


def percent_labels(steps):
    """using locale"""
    locale = QLocale()
    return tuple((step, locale.toString(step) + locale.percent()) for step in steps)


def keyed_combo(labels):
    """A combo whose items carry their stored key as data"""
    combo = QComboBox()
    for key, label in labels:
        combo.addItem(label, key)
    return combo


def select_data(combo, key):
    index = combo.findData(key)
    if index >= 0:
        combo.setCurrentIndex(index)


class PreferencesDialog(QDialog):
    settings_changed = pyqtSignal()

    DEFAULT_SIZE = QSize(40 * units.GRID_UNIT, 26 * units.GRID_UNIT)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(PREFERENCES["title"])
        self.bg_color = QColor(BACKGROUND_COLOR_DEFAULT)
        self.checkerboard_color = QColor(CHECKERBOARD_COLOR_DEFAULT)
        self.fill_color = QColor(BACKGROUND_FILL_DEFAULT)
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
        self.page_list.setCurrentRow(0)

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

        for combo in (
            self.theme_combo,
            self.text_size_combo,
            self.bg_combo,
            self.positioning_combo,
            self.motion_combo,
        ):
            combo.currentIndexChanged.connect(self.update_apply_button)
        self.background_grid.selectionModel().selectionChanged.connect(self.update_apply_button)
        self.background_grid.removal_toggled.connect(self.update_apply_button)
        self.show_available_decks_check.toggled.connect(self.update_apply_button)
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
            ("background", "preferences-desktop-wallpaper", self.build_background_page),
            ("library", LIBRARY_ICON, self.build_library_page),
            ("shortcuts", "configure-shortcuts", self.build_shortcuts_page),
        ]
        if sys.platform == "linux":
            pages.append(("advanced", "preferences-system", self.build_advanced_page))
        return pages

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
        """A Type row, then the rows that belong to the selected type, in one label column"""
        page = QWidget()
        self.background_form = pane_form()

        self.bg_combo = keyed_combo(BACKGROUND_STYLE_LABELS)
        self.bg_combo.currentIndexChanged.connect(self.show_type_rows)
        self.bg_combo.activated.connect(self.select_an_image)
        self.background_form.addRow(PREFERENCES["background_type"], self.bg_combo)

        self.solid_color_btn = self.swatch_button(self.select_solid_color)
        self.background_form.addRow(PREFERENCES["background_colour_label"], self.solid_color_btn)
        self.checkerboard_color_btn = self.swatch_button(self.select_checkerboard_color)
        self.background_form.addRow(
            PREFERENCES["background_colour_label"], self.checkerboard_color_btn
        )
        # Swirl and Aura share this row and its key, so the swirl's fallback matches
        self.hue_row = self.build_hue_row()
        self.background_form.addRow(PREFERENCES["background_hue_label"], self.hue_row)

        self.positioning_combo = keyed_combo(POSITIONING_LABELS)
        self.positioning_combo.currentIndexChanged.connect(self.show_type_rows)
        self.background_form.addRow(PREFERENCES["background_positioning"], self.positioning_combo)
        self.fill_color_btn = self.swatch_button(self.select_fill_color)
        self.background_form.addRow(PREFERENCES["background_fill"], self.fill_color_btn)

        self.images_header = QWidget()
        header = QHBoxLayout(self.images_header)
        header.setContentsMargins(0, units.LARGE_SPACING, 0, 0)
        images_label = typography.apply(
            QLabel(PREFERENCES["background_images"]), typography.Role.HEADING_4
        )
        images_label.setTextFormat(Qt.TextFormat.PlainText)
        header.addWidget(images_label)
        header.addStretch(1)
        self.add_image_btn = QPushButton(QIcon.fromTheme("list-add"), PREFERENCES["background_add"])
        self.add_image_btn.clicked.connect(self.add_images)
        header.addWidget(self.add_image_btn)
        self.background_form.addRow(self.images_header)

        self.background_grid = BackgroundGrid(self.canvas_aspect())
        self.background_grid.files_dropped.connect(self.add_image_files)
        self.background_grid.open_folder_requested.connect(self.open_backgrounds_folder)
        self.background_form.addRow(self.background_grid)

        # The label column keeps the widest type's width, so the combo doesn't change width under
        # the pointer as rows come and go
        form = self.background_form
        widest = max(
            form.labelForField(field).sizeHint().width()
            for field in (
                self.solid_color_btn,
                self.checkerboard_color_btn,
                self.hue_row,
                self.positioning_combo,
                self.fill_color_btn,
            )
        )
        form.labelForField(self.bg_combo).setMinimumWidth(widest)

        page.setLayout(form)
        return page

    def build_hue_row(self):
        """One checkable round swatch per GroundHue, in GROUND_HUES order"""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(units.SMALL_SPACING)
        self.hue_group = QButtonGroup(row)
        self.hue_group.setExclusive(True)
        self.hue_buttons = {}
        for hue_id, hue in GROUND_HUES.items():
            button = QToolButton()
            button.setCheckable(True)
            button.setAutoRaise(True)
            name = PREFERENCES[f"hue_{hue_id}"]
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.setIcon(self.hue_icon(button, hue))
            self.hue_group.addButton(button)
            self.hue_buttons[hue_id] = button
            layout.addWidget(button)
        layout.addStretch(1)
        self.hue_group.buttonToggled.connect(self.update_apply_button)
        return row

    def hue_icon(self, button, hue):
        """A disc of the preset's swirl colours, light at the centre to dark at the rim"""
        size = button.iconSize()
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(QSize(round(size.width() * ratio), round(size.height() * ratio)))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)

        rect = QRectF(0, 0, size.width(), size.height()).adjusted(0.5, 0.5, -0.5, -0.5)
        light, mid, dark = hue.swirl[2], hue.swirl[0], hue.swirl[1]
        gradient = QRadialGradient(rect.center(), rect.width() / 2)
        gradient.setStops(((0.0, light), (0.6, mid), (1.0, dark)))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.palette().mid().color())
        painter.setBrush(gradient)
        painter.drawEllipse(rect)
        painter.end()
        return QIcon(pixmap)

    def selected_hue(self):
        for hue_id, button in self.hue_buttons.items():
            if button.isChecked():
                return hue_id
        return GROUND_HUE_DEFAULT

    def select_hue(self, hue_id):
        button = self.hue_buttons.get(hue_id) or self.hue_buttons[GROUND_HUE_DEFAULT]
        button.setChecked(True)

    @staticmethod
    def swatch_button(slot):
        button = QToolButton()
        button.setToolTip(PREFERENCES["background_colour"])
        button.setAccessibleName(PREFERENCES["background_colour"])
        button.clicked.connect(slot)
        return button

    def canvas_aspect(self):
        """Width over height of the window the canvas is in, for the tiles' shape"""
        window = self.parentWidget().window() if self.parentWidget() else None
        size = window.size() if window else QGuiApplication.primaryScreen().size()
        if size.isEmpty():
            return 16 / 10
        return size.width() / size.height()

    def show_type_rows(self):
        """Only the selected type's own rows"""
        style = self.bg_combo.currentData()
        form = self.background_form
        form.setRowVisible(self.solid_color_btn, style == "solid")
        form.setRowVisible(self.checkerboard_color_btn, style == "checkerboard")
        form.setRowVisible(self.hue_row, style in HUED_STYLES)
        image = style == "image"
        form.setRowVisible(self.positioning_combo, image)
        filled = self.positioning_combo.currentData() in FILLED_POSITIONINGS
        form.setRowVisible(self.fill_color_btn, image and filled)
        form.setRowVisible(self.images_header, image)
        form.setRowVisible(self.background_grid, image)

    def select_an_image(self):
        """Choosing Image with none selected selects the first"""
        grid = self.background_grid
        if self.bg_combo.currentData() != "image" or grid.selected_name():
            return
        names = [name for name in grid.names() if not grid.is_pending(name)]
        if names:
            grid.select_name(names[0])

    def add_images(self):
        suffixes = " ".join("*" + suffix for suffix in sorted(backgrounds.image_suffixes()))
        files, _filter = QFileDialog.getOpenFileNames(
            self,
            PREFERENCES["background_add_title"],
            "",
            f"{PREFERENCES['background_images']} ({suffixes})",
        )
        self.add_image_files(files)

    def add_image_files(self, files):
        """Copy each in; the last one copied becomes the selection"""
        added = [name for name in map(backgrounds.add_background, files) if name]
        if not added:
            return
        grid = self.background_grid
        grid.reload(grid.pending())
        grid.select_name(added[-1])
        select_data(self.bg_combo, "image")

    def open_backgrounds_folder(self):
        folder = backgrounds.backgrounds_base()
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            logger.error(f"Could not open the folder {folder}")

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

    def set_bg_color(self, color):
        self.bg_color = QColor(color)
        self.solid_color_btn.setIcon(self.swatch_icon(self.solid_color_btn, self.bg_color))
        self.update_apply_button()

    def set_fill_color(self, color):
        self.fill_color = QColor(color)
        self.fill_color_btn.setIcon(self.swatch_icon(self.fill_color_btn, self.fill_color))
        self.update_apply_button()

    def set_checkerboard_color(self, color):
        self.checkerboard_color = QColor(color)
        self.checkerboard_color_btn.setIcon(
            self.swatch_icon(self.checkerboard_color_btn, self.checkerboard_color)
        )
        self.update_apply_button()

    def swatch_icon(self, button, color):
        """A rounded square of `color` at `button`'s icon size and the screen's pixel density"""
        size = button.iconSize()
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(QSize(round(size.width() * ratio), round(size.height() * ratio)))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.palette().mid().color())
        painter.setBrush(color)
        # Half a pixel in, so the 1 px border lands on whole pixels
        rect = QRectF(0, 0, size.width(), size.height()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = size.width() / 8
        painter.drawRoundedRect(rect, radius, radius)
        painter.end()
        return QIcon(pixmap)

    def select_solid_color(self):
        color = QColorDialog.getColor(initial=self.bg_color, parent=self)
        if color.isValid():
            self.set_bg_color(color)

    def select_fill_color(self):
        color = QColorDialog.getColor(initial=self.fill_color, parent=self)
        if color.isValid():
            self.set_fill_color(color)

    def select_checkerboard_color(self):
        color = QColorDialog.getColor(initial=self.checkerboard_color, parent=self)
        if color.isValid():
            self.set_checkerboard_color(color)

    def form_state(self):
        """What the form says, in the terms it is stored in"""
        return (
            self.theme_combo.currentData(),
            self.text_size_combo.currentData(),
            self.bg_combo.currentData(),
            self.bg_color.name(),
            self.checkerboard_color.name(),
            self.selected_hue(),
            self.background_grid.selected_name(),
            self.positioning_combo.currentData(),
            self.fill_color.name(),
            self.background_grid.pending(),
            self.motion_combo.currentData(),
            self.canvas_tab_minimap_check.isChecked(),
            self.canvas_guides_check.isChecked(),
            self.show_available_decks_check.isChecked(),
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
        background,
        colour,
        checkerboard_colour,
        hue,
        image,
        positioning,
        fill,
        motion,
        tab_minimap,
        guides,
        show_available,
        hardware_acceleration,
    ):
        select_data(self.theme_combo, theme)
        select_data(self.text_size_combo, text_size)
        select_data(self.bg_combo, background)
        select_data(self.motion_combo, motion)
        self.set_bg_color(colour)
        self.set_checkerboard_color(checkerboard_colour)
        self.select_hue(hue)
        self.background_grid.select_name(image)
        select_data(self.positioning_combo, positioning)
        self.set_fill_color(fill)
        self.canvas_tab_minimap_check.setChecked(tab_minimap)
        self.canvas_guides_check.setChecked(guides)
        self.show_available_decks_check.setChecked(show_available)
        if self.hardware_acceleration_check:
            self.hardware_acceleration_check.setChecked(hardware_acceleration)
        self.show_type_rows()
        self.update_apply_button()

    def load_settings(self):
        settings = get_settings()
        self.background_grid.reload()
        self.show_state(
            ThemeManager.get_instance().get_current_theme().value,
            typography.reading_scale(),
            get_background_style(settings),
            settings.value(BACKGROUND_COLOR_KEY, BACKGROUND_COLOR_DEFAULT),
            settings.value(CHECKERBOARD_COLOR_KEY, CHECKERBOARD_COLOR_DEFAULT),
            ground_hue_id(settings),
            settings.value(BACKGROUND_IMAGE_KEY, BACKGROUND_IMAGE_DEFAULT),
            get_background_positioning(settings),
            settings.value(BACKGROUND_FILL_KEY, BACKGROUND_FILL_DEFAULT),
            get_motion_level(settings),
            bool(settings.value(CANVAS_TAB_MINIMAP_KEY, CANVAS_TAB_MINIMAP_DEFAULT, type=bool)),
            bool(settings.value(CANVAS_GUIDES_KEY, CANVAS_GUIDES_DEFAULT, type=bool)),
            bool(settings.value(SHOW_AVAILABLE_DECKS_KEY, SHOW_AVAILABLE_DECKS_DEFAULT, type=bool)),
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
            BACKGROUND_STYLE_DEFAULT,
            BACKGROUND_COLOR_DEFAULT,
            CHECKERBOARD_COLOR_DEFAULT,
            GROUND_HUE_DEFAULT,
            BACKGROUND_IMAGE_DEFAULT,
            BACKGROUND_POSITIONING_DEFAULT,
            BACKGROUND_FILL_DEFAULT,
            MOTION_LEVEL_DEFAULT,
            CANVAS_TAB_MINIMAP_DEFAULT,
            CANVAS_GUIDES_DEFAULT,
            SHOW_AVAILABLE_DECKS_DEFAULT,
            HARDWARE_ACCELERATION_DEFAULT,
        )
        self.shortcuts_page.reset()

    def apply_settings(self):
        settings = get_settings()
        settings.setValue(BACKGROUND_STYLE_KEY, self.bg_combo.currentData())
        settings.setValue(MOTION_LEVEL_KEY, self.motion_combo.currentData())
        settings.setValue(BACKGROUND_COLOR_KEY, self.bg_color.name())
        settings.setValue(CHECKERBOARD_COLOR_KEY, self.checkerboard_color.name())
        settings.setValue(GROUND_HUE_KEY, self.selected_hue())
        settings.setValue(BACKGROUND_IMAGE_KEY, self.background_grid.selected_name())
        settings.setValue(BACKGROUND_POSITIONING_KEY, self.positioning_combo.currentData())
        settings.setValue(BACKGROUND_FILL_KEY, self.fill_color.name())
        removed = self.background_grid.pending()
        for name in removed:
            backgrounds.remove_background(name)
        if removed:
            self.background_grid.reload()
        settings.setValue(CANVAS_TAB_MINIMAP_KEY, self.canvas_tab_minimap_check.isChecked())
        settings.setValue(CANVAS_GUIDES_KEY, self.canvas_guides_check.isChecked())
        settings.setValue(SHOW_AVAILABLE_DECKS_KEY, self.show_available_decks_check.isChecked())
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
        get_settings().setValue(PREFERENCES_GEOMETRY_KEY, self.saveGeometry())
        super().done(result)
