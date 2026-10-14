from PyQt6.QtCore import QLocale, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.settings import (
    BACKGROUND_COLOR_DEFAULT,
    BACKGROUND_COLOR_KEY,
    BACKGROUND_STYLE_DEFAULT,
    BACKGROUND_STYLE_KEY,
    MOTION_LEVEL_DEFAULT,
    MOTION_LEVEL_KEY,
    PREFERENCES_GEOMETRY_KEY,
    READING_TEXT_SCALE_DEFAULT,
    READING_TEXT_SCALE_STEPS,
    SHOW_AVAILABLE_DECKS_DEFAULT,
    SHOW_AVAILABLE_DECKS_KEY,
    get_background_style,
    get_motion_level,
    get_settings,
)
from tarot_canvas.ui import typography
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.pane_text import pane_form
from tarot_canvas.ui.widgets.places_sidebar import PlacesSidebar
from tarot_canvas.ui.windows.preferences_text import PREFERENCES_TEXT
from tarot_canvas.ui.windows.shortcuts_page import ShortcutsPage
from tarot_canvas.utils.theme_manager import ThemeManager, ThemeType

THEME_LABELS = (
    (ThemeType.SYSTEM.value, "System"),
    (ThemeType.LIGHT.value, "Light"),
    (ThemeType.DARK.value, "Dark"),
)

BACKGROUND_STYLE_LABELS = (
    ("checkerboard", "Checkerboard"),
    ("gradient", "Gradient"),
    ("solid", "Solid Color"),
)

MOTION_LEVEL_LABELS = (
    ("Off", "None"),
    ("Reactive", "Response only"),
    ("Full", "Full"),
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
        self.setWindowTitle("Preferences")
        self.bg_color = QColor(BACKGROUND_COLOR_DEFAULT)
        self.stored_state = None

        self.page_list = PlacesSidebar(
            [
                (QIcon.fromTheme(icon_name), PREFERENCES_TEXT[key], key)
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

        for combo in (self.theme_combo, self.text_size_combo, self.bg_combo, self.motion_combo):
            combo.currentIndexChanged.connect(self.update_apply_button)
        self.show_available_decks_check.toggled.connect(self.update_apply_button)
        self.shortcuts_page.changed.connect(self.update_apply_button)

    def pages(self):
        """The sidebar's pages in order"""
        return [
            ("appearance", "games-config-theme", self.build_appearance_page),
            ("canvas", "draw-rectangle", self.build_canvas_page),
            ("library", "view-list-icons", self.build_library_page),
            ("shortcuts", "configure-shortcuts", self.build_shortcuts_page),
        ]

    def show_page(self, row):
        self.page_stack.setCurrentIndex(row)
        self.page_title.setText(self.page_list.item(row).text())

    def build_appearance_page(self):
        page = QWidget()
        form = pane_form()
        self.theme_combo = keyed_combo(THEME_LABELS)
        form.addRow("Theme:", self.theme_combo)
        self.text_size_combo = keyed_combo(percent_labels(READING_TEXT_SCALE_STEPS))
        form.addRow(PREFERENCES_TEXT["text_size"], self.text_size_combo)
        page.setLayout(form)
        return page

    def build_canvas_page(self):
        page = QWidget()
        form = pane_form()

        self.bg_combo = keyed_combo(BACKGROUND_STYLE_LABELS)
        self.bg_combo.currentIndexChanged.connect(self.update_swatch_visibility)

        self.bg_color_btn = QToolButton()
        self.bg_color_btn.setToolTip(PREFERENCES_TEXT["background_colour"])
        self.bg_color_btn.setAccessibleName(PREFERENCES_TEXT["background_colour"])
        self.bg_color_btn.clicked.connect(self.select_bg_color)
        # Hiding the swatch keeps its room, so the combo doesn't change width under the pointer
        policy = self.bg_color_btn.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.bg_color_btn.setSizePolicy(policy)

        background = QWidget()
        background.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(background)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.bg_combo, 1)
        row.addWidget(self.bg_color_btn)
        form.addRow("Canvas Background:", background)

        self.motion_combo = keyed_combo(MOTION_LEVEL_LABELS)
        form.addRow("Canvas Motion:", self.motion_combo)

        page.setLayout(form)
        return page

    def build_library_page(self):
        page = QWidget()
        form = pane_form()
        # Ghost tiles for catalog decks not installed yet
        self.show_available_decks_check = QCheckBox("Show available decks")
        form.addRow("Library:", self.show_available_decks_check)
        page.setLayout(form)
        return page

    def build_shortcuts_page(self):
        self.shortcuts_page = ShortcutsPage()
        return self.shortcuts_page

    def update_swatch_visibility(self):
        self.bg_color_btn.setVisible(self.bg_combo.currentData() == "solid")

    def set_bg_color(self, color):
        self.bg_color = QColor(color)
        self.bg_color_btn.setIcon(self.swatch_icon(self.bg_color))
        self.update_apply_button()

    def swatch_icon(self, color):
        """A rounded square of `color`, drawn at the screen's pixel density"""
        size = self.bg_color_btn.iconSize()
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

    def select_bg_color(self):
        color = QColorDialog.getColor(initial=self.bg_color, parent=self)
        if color.isValid():
            self.set_bg_color(color)

    def form_state(self):
        """What the form says, in the terms it is stored in"""
        return (
            self.theme_combo.currentData(),
            self.text_size_combo.currentData(),
            self.bg_combo.currentData(),
            self.bg_color.name(),
            self.motion_combo.currentData(),
            self.show_available_decks_check.isChecked(),
            self.shortcuts_page.state(),
        )

    def update_apply_button(self):
        """Apply is offered only while the form differs from what is stored"""
        self.apply_button.setEnabled(
            self.stored_state is not None and self.form_state() != self.stored_state
        )

    def show_state(self, theme, text_size, background, colour, motion, show_available):
        select_data(self.theme_combo, theme)
        select_data(self.text_size_combo, text_size)
        select_data(self.bg_combo, background)
        select_data(self.motion_combo, motion)
        self.set_bg_color(colour)
        self.show_available_decks_check.setChecked(show_available)
        self.update_swatch_visibility()
        self.update_apply_button()

    def load_settings(self):
        settings = get_settings()
        self.show_state(
            ThemeManager.get_instance().get_current_theme().value,
            typography.reading_scale(),
            get_background_style(settings),
            settings.value(BACKGROUND_COLOR_KEY, BACKGROUND_COLOR_DEFAULT),
            get_motion_level(settings),
            bool(settings.value(SHOW_AVAILABLE_DECKS_KEY, SHOW_AVAILABLE_DECKS_DEFAULT, type=bool)),
        )
        self.shortcuts_page.load()
        self.stored_state = self.form_state()
        self.update_apply_button()

    def restore_defaults(self):
        self.show_state(
            ThemeType.SYSTEM.value,
            READING_TEXT_SCALE_DEFAULT,
            BACKGROUND_STYLE_DEFAULT,
            BACKGROUND_COLOR_DEFAULT,
            MOTION_LEVEL_DEFAULT,
            SHOW_AVAILABLE_DECKS_DEFAULT,
        )
        self.shortcuts_page.reset()

    def apply_settings(self):
        settings = get_settings()
        settings.setValue(BACKGROUND_STYLE_KEY, self.bg_combo.currentData())
        settings.setValue(MOTION_LEVEL_KEY, self.motion_combo.currentData())
        settings.setValue(BACKGROUND_COLOR_KEY, self.bg_color.name())
        settings.setValue(SHOW_AVAILABLE_DECKS_KEY, self.show_available_decks_check.isChecked())

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
