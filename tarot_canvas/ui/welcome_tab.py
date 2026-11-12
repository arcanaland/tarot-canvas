import html

from PyQt6.QtCore import QEvent, QSize, Qt, pyqtSlot
from PyQt6.QtGui import QIcon, QPalette, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.about import load_about_data
from tarot_canvas.models import readings
from tarot_canvas.models.reading_events import reading_events
from tarot_canvas.models.spread_events import spread_events
from tarot_canvas.models.welcome_events import welcome_events
from tarot_canvas.settings import get_show_welcome, set_show_welcome
from tarot_canvas.ui import typography
from tarot_canvas.ui.activate_on_return import activate_on_return
from tarot_canvas.ui.canvas.detail import card_unit_size
from tarot_canvas.ui.canvas.saved_canvas import local_qdatetime, reading_label
from tarot_canvas.ui.icons import LIBRARY_ICON, SPREAD_ICON, deck_icon
from tarot_canvas.ui.library.readings.model import reading_icon
from tarot_canvas.ui.library.roles import SubtitleRole
from tarot_canvas.ui.library.row_delegate import IconRowDelegate
from tarot_canvas.ui.library.spreads.model import spread_thumbnail, spread_title
from tarot_canvas.ui.refresh_when_shown import RefreshWhenShown
from tarot_canvas.ui.spread_menu import sections
from tarot_canvas.ui.strings import COMMANDS, MAIN_WINDOW, READINGS
from tarot_canvas.ui.windows.about import ICON_PATH
from tarot_canvas.utils.dates import relative_date

# Cribbing this from Kate (<3)
SPACING = 20
ICON_SIZE = 96
PLACEHOLDER_SCALE = 1.3
PLACEHOLDER_MARGIN = 20
RECENT_MIN_SIZE = QSize(400, 200)
SPREADS_MIN_HEIGHT = 200
SPREAD_ICON_SIZE = QSize(32, 32)
# The page's share of the room left over, against the margins on either side
OUTER_STRETCH = 3
CONTENT_STRETCH = 5

FolderRole = Qt.ItemDataRole.UserRole + 51


def without_mnemonic(text):
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


def shows_part(visible, room, content, part, spacing):
    """Whether a part of the page that gives way shows"""
    if visible:
        return room > content
    return room > content + part + spacing


class Placeholder(QLabel):
    """message inside an empty list"""

    def __init__(self, view, text):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMargin(PLACEHOLDER_MARGIN)
        self.setWordWrap(True)
        self.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        QVBoxLayout(view.viewport()).addWidget(self)
        self._view = view
        self.update_font()

    def update_font(self):
        self.setFont(typography.scaled(self._view.font(), PLACEHOLDER_SCALE))


def _heading(text):
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
    return typography.apply(label, typography.Role.HEADING_2)


def _link(text, slot):
    label = QLabel(f'<a href="#">{html.escape(text)}</a>')
    label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
    label.linkActivated.connect(slot)
    return label


def _list(view):
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setAlternatingRowColors(True)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    activate_on_return(view)
    return view


def _panel(heading, buttons, view):
    """Buttons stacked on the left, the heading over the list on the right"""
    panel = QWidget()
    grid = QGridLayout(panel)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(SPACING)
    grid.addWidget(heading, 0, 1)
    for row, button in enumerate(buttons, start=1):
        grid.addWidget(button, row, 0)
    grid.addWidget(view, 1, 1, len(buttons) + 1, 1)
    grid.setRowStretch(len(buttons) + 1, 1)
    grid.setColumnStretch(1, 1)
    return panel


class WelcomeTab(QScrollArea):
    def __init__(
        self,
        *,
        new_reading_menu,
        new_canvas,
        open_deck,
        open_saved_reading,
        start_reading,
        new_spread,
        manage_spreads,
        show_faqs,
        report_bug,
        get_involved,
        parent=None,
    ):
        super().__init__(parent)
        self._open_saved_reading = open_saved_reading
        self._start_reading = start_reading
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)

        about = load_about_data()
        self.header = QWidget()
        header_row = QHBoxLayout(self.header)
        header_row.setContentsMargins(0, 0, 0, 0)
        icon = QLabel()
        icon.setPixmap(QIcon(str(ICON_PATH)).pixmap(ICON_SIZE, ICON_SIZE))
        self.title = typography.apply(
            QLabel(MAIN_WINDOW["welcome_heading"]), typography.Role.HEADING_1, primary=True
        )
        self.description = QLabel(about.summary)
        about_text = QWidget()
        about_column = QVBoxLayout(about_text)
        about_column.setContentsMargins(0, 0, 0, 0)
        about_column.addWidget(self.title)
        about_column.addWidget(self.description)
        header_row.addStretch(1)
        header_row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(about_text, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addStretch(1)

        new_reading = QPushButton(
            QIcon.fromTheme("media-playback-start"), MAIN_WINDOW["welcome_new_reading"]
        )
        new_reading.setMenu(new_reading_menu(new_reading))
        new_canvas_button = QPushButton(
            QIcon.fromTheme("draw-rectangle"), MAIN_WINDOW["welcome_new_canvas"]
        )
        new_canvas_button.clicked.connect(new_canvas)
        open_deck_button = QPushButton(deck_icon(), MAIN_WINDOW["welcome_open_deck"])
        open_deck_button.clicked.connect(open_deck)
        new_spread_button = QPushButton(QIcon.fromTheme(SPREAD_ICON), COMMANDS["new_spread"])
        new_spread_button.clicked.connect(new_spread)
        manage_spreads_button = QPushButton(
            QIcon.fromTheme(LIBRARY_ICON), MAIN_WINDOW["welcome_manage_spreads"]
        )
        manage_spreads_button.clicked.connect(manage_spreads)
        self.buttons = (
            new_reading,
            new_canvas_button,
            open_deck_button,
            new_spread_button,
            manage_spreads_button,
        )

        self.recent_model = QStandardItemModel(self)
        self.recent_list = _list(QListView())
        self.recent_list.setModel(self.recent_model)
        self.recent_list.setItemDelegate(IconRowDelegate(self.recent_list, preview=False))
        self.recent_list.setMinimumSize(RECENT_MIN_SIZE)
        self.recent_list.activated.connect(self._on_recent_activated)
        self.recent_placeholder = Placeholder(self.recent_list, READINGS["welcome_no_readings"])

        self.spreads_list = _list(QListWidget())
        self.spreads_list.setIconSize(SPREAD_ICON_SIZE)
        self.spreads_list.setMinimumHeight(SPREADS_MIN_HEIGHT)
        self.spreads_list.activated.connect(self._on_spread_activated)
        self.spreads_placeholder = Placeholder(self.spreads_list, MAIN_WINDOW["welcome_no_spreads"])

        self.recent_heading = _heading(MAIN_WINDOW["welcome_recent_readings"])
        recent = _panel(self.recent_heading, self.buttons[:3], self.recent_list)
        spreads_panel = _panel(
            _heading(MAIN_WINDOW["welcome_spreads"]), self.buttons[3:], self.spreads_list
        )

        self.help = QWidget()
        help_column = QVBoxLayout(self.help)
        help_column.setContentsMargins(0, 0, 0, 0)
        self.help_heading = _heading(MAIN_WINDOW["welcome_help"])
        help_column.addWidget(self.help_heading)
        self.help_links = (
            _link(MAIN_WINDOW["welcome_faqs"], show_faqs),
            _link(without_mnemonic(MAIN_WINDOW["report_bug"]), report_bug),
            _link(MAIN_WINDOW["welcome_get_involved"], get_involved),
        )
        for link in self.help_links:
            help_column.addWidget(link, 0, Qt.AlignmentFlag.AlignLeft)
        help_column.addStretch(1)

        self.panels = QGridLayout()
        self.panels.setSpacing(SPACING)
        self.panels.addWidget(recent, 0, 0)
        self.panels.addWidget(self.help, 0, 1)
        self.panels.addWidget(spreads_panel, 1, 0)
        self.panels.setColumnStretch(0, 1)

        self.content = QFrame()
        self.content_column = QVBoxLayout(self.content)
        self.content_column.setSpacing(SPACING)
        self.content_column.addWidget(self.header)
        self.content_column.addLayout(self.panels, 1)

        self.show_at_startup = QCheckBox(MAIN_WINDOW["welcome_show_at_startup"])
        self.show_at_startup.setChecked(get_show_welcome())
        self.show_at_startup.toggled.connect(set_show_welcome)
        self.content_column.addWidget(self.show_at_startup, 0, Qt.AlignmentFlag.AlignHCenter)

        page = QWidget()
        root = QGridLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.content, 1, 1)
        for index, stretch in enumerate((OUTER_STRETCH, CONTENT_STRETCH, OUTER_STRETCH)):
            root.setRowStretch(index, stretch)
            root.setColumnStretch(index, stretch)
        self.setWidget(page)

        self.refresh_readings()
        self.refresh_spreads()
        self._update_button_widths()
        self._on_readings_changed = RefreshWhenShown(self, self.refresh_readings)
        reading_events().readings_changed.connect(self._on_readings_changed.changed)
        spread_events().spreads_changed.connect(self.refresh_spreads)
        welcome_events().show_at_startup_changed.connect(self.follow_show_at_startup)

    @pyqtSlot(bool)
    def follow_show_at_startup(self, shown):
        self.show_at_startup.setChecked(shown)

    @pyqtSlot()
    def refresh_readings(self):
        self.recent_model.clear()
        unit = card_unit_size()
        for folder, reading in readings.scan():
            item = QStandardItem(
                reading_icon(reading, unit), reading_label(reading.question, reading.date)
            )
            item.setData(relative_date(local_qdatetime(reading.date).date()), SubtitleRole)
            item.setData(str(folder), FolderRole)
            item.setEditable(False)
            self.recent_model.appendRow(item)
        self.recent_placeholder.setVisible(self.recent_model.rowCount() == 0)

    @pyqtSlot()
    def refresh_spreads(self):
        self.spreads_list.clear()
        unit = card_unit_size()
        for rows in sections():
            for folder, spread in rows:
                item = QListWidgetItem(spread_thumbnail(spread, unit), spread_title(spread))
                item.setData(FolderRole, str(folder))
                self.spreads_list.addItem(item)
        self.spreads_placeholder.setVisible(self.spreads_list.count() == 0)

    def _on_recent_activated(self, index):
        if index.isValid():
            self._open_saved_reading(index.data(FolderRole))

    def _on_spread_activated(self, index):
        if index.isValid():
            self._start_reading(index.data(FolderRole))

    def _update_button_widths(self):
        for button in self.buttons:
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)
        width = max(button.sizeHint().width() for button in self.buttons)
        for button in self.buttons:
            button.setFixedWidth(width)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def update_layout(self):
        """Hide the header when the page is too short and Help when it is too narrow"""
        self.help_heading.setMinimumHeight(self.recent_heading.height())
        changed = False
        header = shows_part(
            self.header.isVisibleTo(self),
            self.height(),
            self.content.height(),
            self.header.sizeHint().height(),
            self.content_column.spacing(),
        )
        if header != self.header.isVisibleTo(self):
            self.header.setVisible(header)
            changed = True
        help_shown = shows_part(
            self.help.isVisibleTo(self),
            self.width(),
            self.content.width(),
            self.help.sizeHint().width(),
            self.panels.horizontalSpacing(),
        )
        if help_shown != self.help.isVisibleTo(self):
            self.help.setVisible(help_shown)
            changed = True
        return changed

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            self.update_layout()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_layout()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.FontChange:
            self.recent_placeholder.update_font()
            self.spreads_placeholder.update_font()
            self._update_button_widths()
        super().changeEvent(event)
