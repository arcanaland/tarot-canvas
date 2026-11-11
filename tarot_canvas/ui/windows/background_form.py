"""The rows that choose a Ground: Preferences' Background page, and a canvas's own panel"""

from PyQt6.QtCore import QRectF, QSize, Qt, QUrl, pyqtSignal
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
    QColorDialog,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QWidget,
)

from tarot_canvas.models import backgrounds
from tarot_canvas.models.ground import FILLED_POSITIONINGS, HUED_STYLES, Ground
from tarot_canvas.ui import typography, units
from tarot_canvas.ui.canvas.ground import GROUND_HUE_DEFAULT, GROUND_HUES
from tarot_canvas.ui.strings import PREFERENCES
from tarot_canvas.ui.widgets.pane_text import pane_form
from tarot_canvas.ui.windows.background_grid import BackgroundGrid
from tarot_canvas.utils.logger import logger

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


def canvas_aspect(widget):
    """Width over height of the window widget is in, for the tiles' shape"""
    window = widget.window() if widget is not None else None
    size = window.size() if window else QGuiApplication.primaryScreen().size()
    if size.isEmpty():
        return 16 / 10
    return size.width() / size.height()


class BackgroundForm(QWidget):
    """A Type row, then the rows that belong to the selected type, in one label column.

    The compact layout is a panel's: the images are one scrolling strip ending in an Add
    button, and its tiles offer no Remove or Open Folder.
    """

    # The ground the form shows changed, or a pending removal was set or undone
    changed = pyqtSignal()

    def __init__(self, aspect, compact=False, parent=None):
        super().__init__(parent)
        self.compact = compact
        self.bg_color = QColor(Ground.color)
        self.checkerboard_color = QColor(Ground.checkerboard_color)
        self.fill_color = QColor(Ground.fill)

        # The margins are whoever holds the form's
        self.rows = pane_form()
        self.rows.setContentsMargins(0, 0, 0, 0)

        self.bg_combo = keyed_combo(BACKGROUND_STYLE_LABELS)
        self.bg_combo.currentIndexChanged.connect(self.show_type_rows)
        self.bg_combo.activated.connect(self.select_an_image)
        self.rows.addRow(PREFERENCES["background_type"], self.bg_combo)

        self.background_grid = BackgroundGrid(aspect, tile_actions=not compact, strip=compact)
        self.background_grid.files_dropped.connect(self.add_image_files)
        self.background_grid.open_folder_requested.connect(self.open_backgrounds_folder)

        if compact:
            self.add_image_btn = QToolButton()
            self.add_image_btn.setIcon(QIcon.fromTheme("list-add"))
            self.add_image_btn.setToolTip(PREFERENCES["background_add"])
            self.add_image_btn.setAccessibleName(PREFERENCES["background_add"])
            # The strip and its Add button, under the Type row as the tiles are under it in
            # Preferences
            self.images_header = QWidget()
            strip = QHBoxLayout(self.images_header)
            strip.setContentsMargins(0, 0, 0, 0)
            strip.addWidget(self.background_grid, 1)
            strip.addWidget(self.add_image_btn, 0, Qt.AlignmentFlag.AlignVCenter)
            self.rows.addRow(self.images_header)
            self.image_rows = (self.images_header,)
        else:
            self.add_image_btn = QPushButton(
                QIcon.fromTheme("list-add"), PREFERENCES["background_add"]
            )
        self.add_image_btn.clicked.connect(self.add_images)

        self.solid_color_btn = self.swatch_button(self.select_solid_color)
        self.rows.addRow(PREFERENCES["background_colour_label"], self.solid_color_btn)
        self.checkerboard_color_btn = self.swatch_button(self.select_checkerboard_color)
        self.rows.addRow(PREFERENCES["background_colour_label"], self.checkerboard_color_btn)
        # Swirl and Aura share this row and its key, so the swirl's fallback matches
        self.hue_row = self.build_hue_row()
        self.rows.addRow(PREFERENCES["background_hue_label"], self.hue_row)

        self.positioning_combo = keyed_combo(POSITIONING_LABELS)
        self.positioning_combo.currentIndexChanged.connect(self.show_type_rows)
        self.rows.addRow(PREFERENCES["background_positioning"], self.positioning_combo)
        self.fill_color_btn = self.swatch_button(self.select_fill_color)
        self.rows.addRow(PREFERENCES["background_fill"], self.fill_color_btn)

        if not compact:
            self.images_header = QWidget()
            header = QHBoxLayout(self.images_header)
            header.setContentsMargins(0, units.LARGE_SPACING, 0, 0)
            images_label = typography.apply(
                QLabel(PREFERENCES["background_images"]), typography.Role.HEADING_4
            )
            images_label.setTextFormat(Qt.TextFormat.PlainText)
            header.addWidget(images_label)
            header.addStretch(1)
            header.addWidget(self.add_image_btn)
            self.rows.addRow(self.images_header)
            self.rows.addRow(self.background_grid)
            self.image_rows = (self.images_header, self.background_grid)

        # The label column keeps the widest type's width, so the combo doesn't change width under
        # the pointer as rows come and go
        widest = max(
            self.rows.labelForField(field).sizeHint().width()
            for field in (
                self.solid_color_btn,
                self.checkerboard_color_btn,
                self.hue_row,
                self.positioning_combo,
                self.fill_color_btn,
            )
        )
        self.rows.labelForField(self.bg_combo).setMinimumWidth(widest)
        self.setLayout(self.rows)

        for combo in (self.bg_combo, self.positioning_combo):
            combo.currentIndexChanged.connect(self.changed)
        self.background_grid.selectionModel().selectionChanged.connect(self.changed)
        self.background_grid.removal_toggled.connect(self.changed)
        self.hue_group.buttonToggled.connect(self._on_hue_toggled)

        self.set_ground(Ground())

    # -- building ----------------------------------------------------------

    def build_hue_row(self):
        """One checkable round swatch per GroundHue, in GROUND_HUES order"""
        row = QWidget()
        layout = QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(units.SMALL_SPACING)
        self.hue_group = QButtonGroup(row)
        self.hue_group.setExclusive(True)
        self.hue_buttons = {}
        for column, (hue_id, hue) in enumerate(GROUND_HUES.items()):
            button = QToolButton()
            button.setCheckable(True)
            button.setAutoRaise(True)
            name = PREFERENCES[f"hue_{hue_id}"]
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.setIcon(self.hue_icon(button, hue))
            self.hue_group.addButton(button)
            self.hue_buttons[hue_id] = button
            layout.addWidget(button, 0, column)
        layout.setColumnStretch(len(GROUND_HUES), 1)
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

    @staticmethod
    def swatch_button(slot):
        button = QToolButton()
        button.setToolTip(PREFERENCES["background_colour"])
        button.setAccessibleName(PREFERENCES["background_colour"])
        button.clicked.connect(slot)
        return button

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

    # -- the ground --------------------------------------------------------

    def ground(self):
        """What the form says"""
        return Ground(
            style=self.bg_combo.currentData(),
            hue=self.selected_hue(),
            color=self.bg_color.name(),
            checkerboard_color=self.checkerboard_color.name(),
            image=self.background_grid.selected_name(),
            positioning=self.positioning_combo.currentData(),
            fill=self.fill_color.name(),
        )

    def set_ground(self, ground):
        select_data(self.bg_combo, ground.style)
        self.set_bg_color(ground.color)
        self.set_checkerboard_color(ground.checkerboard_color)
        self.select_hue(ground.hue)
        self.background_grid.select_name(ground.image)
        select_data(self.positioning_combo, ground.positioning)
        self.set_fill_color(ground.fill)
        self.show_type_rows()

    def setRowsEnabled(self, enabled):
        """Every row, its label with it"""
        self.setEnabled(enabled)

    def reload(self):
        """Re-read the backgrounds directory"""
        self.background_grid.reload()

    def pending_removals(self):
        return self.background_grid.pending()

    def commit_removals(self):
        """Remove the images marked for removal"""
        removed = self.background_grid.pending()
        for name in removed:
            backgrounds.remove_background(name)
        if removed:
            self.background_grid.reload()

    def selected_hue(self):
        for hue_id, button in self.hue_buttons.items():
            if button.isChecked():
                return hue_id
        return GROUND_HUE_DEFAULT

    def select_hue(self, hue_id):
        button = self.hue_buttons.get(hue_id) or self.hue_buttons[GROUND_HUE_DEFAULT]
        button.setChecked(True)

    def _on_hue_toggled(self, _button, checked):
        # The one turned on, not the one turned off with it
        if checked:
            self.changed.emit()

    def set_bg_color(self, color):
        self.bg_color = QColor(color)
        self.solid_color_btn.setIcon(self.swatch_icon(self.solid_color_btn, self.bg_color))
        self.changed.emit()

    def set_fill_color(self, color):
        self.fill_color = QColor(color)
        self.fill_color_btn.setIcon(self.swatch_icon(self.fill_color_btn, self.fill_color))
        self.changed.emit()

    def set_checkerboard_color(self, color):
        self.checkerboard_color = QColor(color)
        self.checkerboard_color_btn.setIcon(
            self.swatch_icon(self.checkerboard_color_btn, self.checkerboard_color)
        )
        self.changed.emit()

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

    # -- rows --------------------------------------------------------------

    def show_type_rows(self):
        """Only the selected type's own rows"""
        style = self.bg_combo.currentData()
        rows = self.rows
        rows.setRowVisible(self.solid_color_btn, style == "solid")
        rows.setRowVisible(self.checkerboard_color_btn, style == "checkerboard")
        rows.setRowVisible(self.hue_row, style in HUED_STYLES)
        image = style == "image"
        rows.setRowVisible(self.positioning_combo, image)
        filled = self.positioning_combo.currentData() in FILLED_POSITIONINGS
        rows.setRowVisible(self.fill_color_btn, image and filled)
        for row in self.image_rows:
            rows.setRowVisible(row, image)

    # -- images ------------------------------------------------------------

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
