import contextlib
import os
import sys
from functools import partial
from importlib.resources import files

from PyQt6.QtCore import QEvent, QObject, Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QDesktopServices,
    QGuiApplication,
    QIcon,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.about import load_about_data
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.settings import (
    EXPLORER_VISIBLE_DEFAULT,
    EXPLORER_VISIBLE_KEY,
    MAIN_WINDOW_GEOMETRY_KEY,
    SHOW_AVAILABLE_DECKS_DEFAULT,
    SHOW_AVAILABLE_DECKS_KEY,
    get_settings,
)
from tarot_canvas.ui import commands, focused_text, typography
from tarot_canvas.ui.command_palette import CommandPalette
from tarot_canvas.ui.commands import Scope, set_tooltip_with_keys
from tarot_canvas.ui.commands_text import COMMANDS_TEXT
from tarot_canvas.ui.components.card_explorer import CardExplorerPanel
from tarot_canvas.ui.library.catalog_client import deck_catalog
from tarot_canvas.ui.library.deck_downloads import deck_downloads
from tarot_canvas.ui.library.download_text import DOWNLOAD_TEXT
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab
from tarot_canvas.ui.tabs.library_tab import LibraryTab
from tarot_canvas.ui.widgets.document_tabs import DocumentTabs
from tarot_canvas.ui.widgets.placeholder_message import tinted_icon
from tarot_canvas.ui.widgets.toast import Toast
from tarot_canvas.ui.windows.about import AboutDialog, app_icon
from tarot_canvas.ui.windows.log_viewer import LogViewerDialog
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.theme_manager import ThemeManager, ThemeType

ICON_PATH = files("tarot_canvas.resources.icons").joinpath("icon.png")
WELCOME_TAB_ICON = files("tarot_canvas.resources.icons").joinpath("esoterica.svg")
WELCOME_TAB_NAME = "welcome"  # objectName of its page

# The Go menu's entries, in its groups
GO_GROUPS = (
    ("previous", "next"),
    ("first", "last", "random"),
    ("previous_deck", "next_deck"),
)
GO_PLACES = tuple(where for group in GO_GROUPS for where in group)

# Each Edit entry and the BaseTab method it asks, with can_ before it
TAB_EDITS = {
    "cut": "cut_card",
    "copy": "copy_card",
    "paste": "paste_card",
    "delete": "delete",
    "select_all": "select_all",
    "deselect": "deselect",
}


class TabBarEventFilter(QObject):
    close_tab_requested = pyqtSignal(int)  # Signal with tab index
    new_tab_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._middle_press_index = -1

    def eventFilter(self, obj, event):
        """Filter events for the tab bar"""
        tab_bar = obj
        if event.type() == QEvent.Type.MouseButtonDblClick:
            # In document mode the bar runs on past its tabs up to the corner buttons
            if (
                event.button() == Qt.MouseButton.LeftButton
                and tab_bar.tabAt(event.position().toPoint()) == -1
            ):
                self.new_tab_requested.emit()
        elif (
            event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.MiddleButton
        ):
            self._middle_press_index = tab_bar.tabAt(event.position().toPoint())
            return True  # See the release branch
        elif (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.MiddleButton
        ):
            pressed, self._middle_press_index = self._middle_press_index, -1
            if pressed != -1 and tab_bar.tabAt(event.position().toPoint()) == pressed:
                self.close_tab_requested.emit(pressed)
            return True
        return False  # Always pass the event on


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Explicitly set application and window class names
        self.setObjectName("tarot-canvas")
        QApplication.setApplicationName("tarot-canvas")

        # Try to force the window class name at a lower level
        if hasattr(self.windowHandle(), "setWindowClass"):
            self.windowHandle().setWindowClass("tarot-canvas", "tarot-canvas")

        self.setWindowTitle("Tarot Canvas")
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.setGeometry(100, 100, 950, 600)
        geometry = get_settings().value(MAIN_WINDOW_GEOMETRY_KEY)
        if geometry is not None:
            self.restoreGeometry(geometry)

        # The tab currently fullscreened, and the chrome state to put back
        self.fullscreen_tab = None
        self._pre_fullscreen = None

        # The visible tab, remembered so the one being left can write what it holds
        self.previous_tab = None

        # Initialize theme manager
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.on_theme_changed)

        self.create_menus()
        self.init_ui()

        # The window's, not a library's: a download outlives the library that started it
        self.toast = Toast(self.tab_widget)
        deck_downloads().installed.connect(self.on_deck_installed)

        QGuiApplication.clipboard().dataChanged.connect(self.update_edit_actions)
        self.update_edit_actions()
        self.update_zoom_actions()

    def create_menus(self):
        # Create menu bar
        menu_bar = self.menuBar()

        detached = {
            "window.new_canvas",
            "window.new_library",
            "window.new_card_view",
            "window.open_deck",
            "window.close_tab",
            "window.quit",
            "window.card_explorer",
            "window.preferences",
            *(f"window.go_{where}" for where in GO_PLACES),
        }
        self.window_actions = actions = commands.bind(
            self,
            Scope.WINDOW,
            {
                "window.new_canvas": self.new_canvas_tab,
                "window.new_library": self.new_library_tab,
                "window.new_card_view": self.new_card_view_tab,
                "window.open_deck": self.open_deck,
                "window.close_tab": self.close_current_tab,
                "window.quit": self.close,
                "window.cut": partial(self.edit, "cut"),
                "window.copy_card": partial(self.edit, "copy"),
                "window.paste_card": partial(self.edit, "paste"),
                "window.delete": partial(self.edit, "delete"),
                "window.select_all": partial(self.edit, "select_all"),
                "window.deselect": partial(self.edit, "deselect"),
                "window.find": self.find,
                "window.card_explorer": lambda: self.toggle_card_explorer(
                    self.explorer_action.isChecked()
                ),
                "window.fullscreen": self.toggle_tab_fullscreen,
                "window.zoom_in": partial(self.zoom, "in"),
                "window.zoom_out": partial(self.zoom, "out"),
                "window.reset_zoom": partial(self.zoom, "reset"),
                **{f"window.go_{where}": partial(self.go, where) for where in GO_PLACES},
                "window.find_card": self.show_command_palette,
                "window.preferences": self.show_preferences,
            },
            detached=detached,
        )

        # File menu
        file_menu = menu_bar.addMenu("&File")

        self.new_canvas_action = actions["window.new_canvas"]
        self.new_library_action = actions["window.new_library"]
        self.new_card_view_action = actions["window.new_card_view"]
        file_menu.addActions(
            [self.new_canvas_action, self.new_library_action, self.new_card_view_action]
        )
        file_menu.addSeparator()
        file_menu.addAction(actions["window.open_deck"])
        file_menu.addSeparator()
        file_menu.addAction(actions["window.close_tab"])
        file_menu.addSeparator()
        file_menu.addAction(actions["window.quit"])

        # Edit menu
        edit_menu = menu_bar.addMenu("&Edit")
        edit_menu.aboutToShow.connect(self.update_edit_actions)

        # On the window as well, so they work with the menu bar hidden in fullscreen
        self.copy_card_action = actions["window.copy_card"]
        self.paste_card_action = actions["window.paste_card"]
        self.edit_actions = {
            "cut": actions["window.cut"],
            "copy": self.copy_card_action,
            "paste": self.paste_card_action,
            "delete": actions["window.delete"],
            "select_all": actions["window.select_all"],
            "deselect": actions["window.deselect"],
        }
        edit_menu.addActions([self.edit_actions[how] for how in ("cut", "copy", "paste", "delete")])
        edit_menu.addSeparator()
        edit_menu.addActions([self.edit_actions["select_all"], self.edit_actions["deselect"]])
        edit_menu.addSeparator()
        edit_menu.addAction(actions["window.find"])

        # View menu
        view_menu = menu_bar.addMenu("&View")

        self.explorer_action = actions["window.card_explorer"]
        self.explorer_action.setCheckable(True)
        self.explorer_action.setChecked(True)  # Set checked by default
        view_menu.addAction(self.explorer_action)

        view_menu.addSeparator()

        self.fullscreen_tab_action = actions["window.fullscreen"]
        self.fullscreen_tab_action.setCheckable(True)
        view_menu.addAction(self.fullscreen_tab_action)

        # Zoom stuff
        view_menu.addSeparator()
        self.zoom_in_action = actions["window.zoom_in"]
        self.zoom_out_action = actions["window.zoom_out"]
        self.reset_zoom_action = actions["window.reset_zoom"]
        view_menu.addActions([self.zoom_in_action, self.zoom_out_action, self.reset_zoom_action])
        typography.events().reading_scale_changed.connect(self.update_zoom_actions)
        # Which of the two they act on moves with the focus, and the art's zoom with the wheel
        QApplication.instance().focusChanged.connect(self.on_focus_changed)
        view_menu.aboutToShow.connect(self.update_zoom_actions)

        # ------------- Go menu -----------

        go_menu = menu_bar.addMenu("&Go")
        go_menu.aboutToShow.connect(self.update_go_actions)
        self.go_actions = {where: actions[f"window.go_{where}"] for where in GO_PLACES}
        for group in GO_GROUPS:
            go_menu.addActions([self.go_actions[where] for where in group])
            go_menu.addSeparator()

        # On the window as well, so Ctrl+P works with the menu bar hidden in fullscreen
        self.find_card_action = actions["window.find_card"]
        go_menu.addAction(self.find_card_action)

        self.add_tab_number_shortcuts()

        # Tools menu
        tools_menu = menu_bar.addMenu("&Tools")

        # Add Log Viewer action
        log_viewer_action = QAction("&Log Viewer", self)
        log_viewer_action.setIcon(QIcon.fromTheme("view-list-text"))
        log_viewer_action.triggered.connect(self.show_log_viewer)
        tools_menu.addAction(log_viewer_action)

        settings_menu = menu_bar.addMenu("&Settings")

        theme_menu = QMenu("&Theme", self)
        theme_menu.setIcon(QIcon.fromTheme("games-config-theme"))
        settings_menu.addMenu(theme_menu)

        # Create a theme action group for radio behavior; the radio mark is the icon
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        # System theme action
        system_theme_action = QAction("&System Default", self)
        system_theme_action.setCheckable(True)
        system_theme_action.triggered.connect(lambda: self.change_theme(ThemeType.SYSTEM))
        theme_group.addAction(system_theme_action)
        theme_menu.addAction(system_theme_action)

        # Light theme action
        light_theme_action = QAction("&Light", self)
        light_theme_action.setCheckable(True)
        light_theme_action.triggered.connect(lambda: self.change_theme(ThemeType.LIGHT))
        theme_group.addAction(light_theme_action)
        theme_menu.addAction(light_theme_action)

        # Dark theme action
        dark_theme_action = QAction("&Dark", self)
        dark_theme_action.setCheckable(True)
        dark_theme_action.triggered.connect(lambda: self.change_theme(ThemeType.DARK))
        theme_group.addAction(dark_theme_action)
        theme_menu.addAction(dark_theme_action)

        # Set the checked state based on current theme
        current_theme = ThemeManager.get_instance().get_current_theme()
        if current_theme == ThemeType.SYSTEM:
            system_theme_action.setChecked(True)
        elif current_theme == ThemeType.LIGHT:
            light_theme_action.setChecked(True)
        elif current_theme == ThemeType.DARK:
            dark_theme_action.setChecked(True)

        # Store theme actions for later reference
        self.theme_actions = {
            ThemeType.SYSTEM: system_theme_action,
            ThemeType.LIGHT: light_theme_action,
            ThemeType.DARK: dark_theme_action,
        }

        settings_menu.addSeparator()

        # On macOS Qt moves this to the application menu
        self.preferences_action = actions["window.preferences"]
        self.preferences_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        settings_menu.addAction(self.preferences_action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")

        faq_action = QAction("&Frequently Asked Questions", self)
        faq_action.setIcon(QIcon.fromTheme("help-contents"))
        faq_action.triggered.connect(self.show_faqs)
        help_menu.addAction(faq_action)

        report_bug_action = QAction("&Report Bug", self)
        report_bug_action.setIcon(QIcon.fromTheme("tools-report-bug"))
        report_bug_action.triggered.connect(self.report_bug)
        help_menu.addAction(report_bug_action)

        help_menu.addSeparator()

        about_action = QAction("&About Tarot Canvas", self)
        about_action.setIcon(app_icon(load_about_data().app_id))
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def init_ui(self):
        # Create main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)

        # Create splitter for explorer panel and tab area
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(1)

        # Create and add card explorer panel
        self.card_explorer = CardExplorerPanel()
        self.card_explorer.card_action_requested.connect(self.on_explorer_card_selected)
        self.card_explorer.card_action_requested.connect(self.on_card_action_requested)
        self.card_explorer.close_requested.connect(lambda: self.set_card_explorer_visible(False))
        self.card_explorer.show()
        self.main_splitter.addWidget(self.card_explorer)

        # Create right side container
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Create tab widget
        self.tab_widget = DocumentTabs()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)

        self.tab_bar_filter = TabBarEventFilter(self)
        self.tab_widget.tabBar().installEventFilter(self.tab_bar_filter)
        self.tab_bar_filter.close_tab_requested.connect(self.close_tab)
        self.tab_bar_filter.new_tab_requested.connect(self.new_canvas_action.trigger)

        tab_bar = self.tab_widget.tabBar()
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self.show_tab_context_menu)

        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.tab_widget.setMovable(True)

        # + on the tab bar
        new_tab_button = QToolButton()
        new_tab_button.setAutoRaise(True)
        new_tab_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        new_tab_button.setDefaultAction(self.new_canvas_action)
        new_tab_icon = QIcon.fromTheme("tab-new", QIcon.fromTheme("list-add"))
        new_tab_button.setIcon(new_tab_icon)
        if new_tab_icon.isNull():
            new_tab_button.setText("+")
            new_tab_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        else:
            new_tab_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        set_tooltip_with_keys(new_tab_button, "New tab", self.new_canvas_action)

        new_tab_menu = QMenu(new_tab_button)
        new_tab_menu.addAction(self.new_canvas_action)
        new_tab_menu.addAction(self.new_library_action)
        new_tab_menu.addAction(self.new_card_view_action)
        new_tab_button.setMenu(new_tab_menu)

        # Create search button and put it in the tab corner
        search_button = QToolButton()
        search_button.setIcon(QIcon.fromTheme("search", QIcon.fromTheme("edit-find")))
        set_tooltip_with_keys(search_button, "Search Cards", self.find_card_action)
        search_button.clicked.connect(self.show_command_palette)

        # Style the button to show only the icon without borders or background
        search_button.setStyleSheet("""
            QToolButton {
                border: none;
                background-color: transparent;
                margin: 2px;
            }
            QToolButton:hover {
                background-color: rgba(128, 128, 128, 0.2);
                border-radius: 2px;
            }
        """)

        # shared corner container with the + and search
        corner = QWidget()
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(0)
        corner_layout.addWidget(new_tab_button)
        corner_layout.addWidget(search_button)
        self.tab_widget.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        right_layout.addWidget(self.tab_widget)

        # Add the right container to the splitter
        self.main_splitter.addWidget(right_container)
        # A growing window widens the tabs, never the explorer
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)

        self.size_splitter_to_explorer()

        # Come back the way the previous session left it
        visible = get_settings().value(EXPLORER_VISIBLE_KEY, EXPLORER_VISIBLE_DEFAULT, type=bool)
        self.apply_card_explorer_visible(bool(visible))

        main_layout.addWidget(self.main_splitter)

        # Set the central widget
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Add a welcome tab
        self.add_welcome_tab()

    def add_welcome_tab(self):
        welcome_tab = QWidget()
        welcome_tab.setObjectName(WELCOME_TAB_NAME)
        layout = QVBoxLayout()

        label = QLabel("Welcome to Tarot Canvas!")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Add app icon in the center
        icon_label = QLabel()
        icon_pixmap = QIcon(str(ICON_PATH)).pixmap(128, 128)
        icon_label.setPixmap(icon_pixmap)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # Change label text
        welcome_label = QLabel("Select a card on the left or choose an option below:")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(welcome_label)

        # Button container
        button_layout = QHBoxLayout()

        # Buttons for different tab types
        canvas_btn = QPushButton(QIcon.fromTheme("draw-rectangle"), "New Canvas")
        canvas_btn.clicked.connect(self.new_canvas_tab)
        button_layout.addWidget(canvas_btn)

        deck_btn = QPushButton(QIcon.fromTheme("view-grid"), "Open Standard Deck")
        deck_btn.clicked.connect(self.open_reference_deck)
        button_layout.addWidget(deck_btn)

        library_btn = QPushButton(QIcon.fromTheme("view-list-icons"), "Deck Library")
        library_btn.clicked.connect(self.new_library_tab)
        button_layout.addWidget(library_btn)

        card_btn = QPushButton(QIcon.fromTheme("roll"), "Pick Random Card")
        card_btn.clicked.connect(self.new_card_view_tab)
        button_layout.addWidget(card_btn)

        layout.addLayout(button_layout)
        welcome_tab.setLayout(layout)

        self.tab_widget.addTab(welcome_tab, tinted_icon(WELCOME_TAB_ICON), "Welcome")

    def close_welcome_tab(self):
        """Close the welcome tab if it exists"""
        for i in range(self.tab_widget.count()):
            if self.is_welcome_tab(self.tab_widget.widget(i)):
                self.tab_widget.removeTab(i)
                break

    def new_canvas_tab(self):
        canvas_tab = CanvasTab()
        canvas_tab.navigation_requested.connect(self.handle_tab_navigation)
        self.close_welcome_tab()
        canvas_tab.tab_name = self.next_canvas_name()
        self.tab_widget.addTab(canvas_tab, canvas_tab.tab_name)
        self.tab_widget.setCurrentWidget(canvas_tab)
        return canvas_tab

    def new_canvas_from_cards(self, cards, deck):
        canvas_tab = self.new_canvas_tab()
        canvas_tab.place_cards([(card, deck, False) for card in cards])
        return canvas_tab

    def next_canvas_name(self):
        """Canvas, then Canvas (2), Canvas (3)..., reusing the lowest name no tab holds"""
        taken = {self.tab_widget.tabText(i) for i in range(self.tab_widget.count())}
        name, n = "Canvas", 1
        while name in taken:
            n += 1
            name = f"Canvas ({n})"
        return name

    def show_tab_context_menu(self, pos):
        tab_bar = self.tab_widget.tabBar()
        index = tab_bar.tabAt(pos)
        if index == -1:
            return
        menu = self.tab_context_menu(index)
        menu.exec(tab_bar.mapToGlobal(pos))
        menu.deleteLater()

    def tab_context_menu(self, tab_index):
        """The right-click menu for the tab at tab_index"""
        menu = QMenu(self)
        rename = menu.addAction(
            QIcon.fromTheme("edit-rename"),
            COMMANDS_TEXT["rename_tab"],
            partial(self.show_tab_rename_dialog, tab_index),
        )
        tab = self.tab_widget.widget(tab_index)
        rename.setEnabled(self.is_renamable_tab(tab))
        close = menu.addAction(
            QIcon.fromTheme("tab-close"),
            COMMANDS_TEXT["close_this_tab"],
            partial(self.close_tab, tab_index),
        )
        close.setEnabled(not self.is_welcome_tab(tab))  # closing it would only reopen it
        return menu

    @staticmethod
    def is_welcome_tab(tab):
        return tab is not None and tab.objectName() == WELCOME_TAB_NAME

    @staticmethod
    def is_renamable_tab(tab):
        return tab is not None and hasattr(tab, "id") and tab.id.startswith("canvas_")

    def show_tab_rename_dialog(self, tab_index):
        """Show a dialog to rename the tab at the given index"""
        tab = self.tab_widget.widget(tab_index)
        if not self.is_renamable_tab(tab):
            return  # Only canvas tabs are renamable

        current_name = self.tab_widget.tabText(tab_index)
        new_name, ok = QInputDialog.getText(
            self, "Rename Canvas", "Enter a new name for this canvas:", text=current_name
        )

        if ok and new_name:
            tab.tab_name = new_name
            tab.tab_label_changed.emit()

    def add_card_tab(self, card_tab):
        """Adopt a card view tab. Every construction site must come through here."""
        card_tab.navigation_requested.connect(self.handle_tab_navigation)
        self.close_welcome_tab()
        self.tab_widget.addTab(card_tab, "")
        self.tab_widget.setCurrentWidget(card_tab)
        return card_tab

    def handle_tab_navigation(self, action, data):
        """Handle navigation between tabs"""
        if action == "open_card_view":
            # Extract the data
            card = data.get("card")
            deck = data.get("deck")
            source_tab_id = data.get("source_tab_id")

            # Check if a tab for this card already exists
            for i in range(self.tab_widget.count()):
                tab = self.tab_widget.widget(i)
                if (
                    hasattr(tab, "id")
                    and hasattr(tab, "card")
                    and tab.card
                    and tab.card.get("id") == card.get("id")
                ):
                    # Tab exists, just select it
                    self.tab_widget.setCurrentWidget(tab)
                    return

            # Create a new card view tab
            card_tab = CardViewTab(card=card, deck=deck, source_tab_id=source_tab_id)
            self.add_card_tab(card_tab)

        elif action == "open_deck_view":
            deck_path = data.get("deck_path")
            self.new_deck_view_tab(deck_path=deck_path)

        elif action == "navigate":
            # Navigate to a specific tab by ID
            tab_id = data
            for i in range(self.tab_widget.count()):
                tab = self.tab_widget.widget(i)
                if hasattr(tab, "id") and tab.id == tab_id:
                    self.tab_widget.setCurrentWidget(tab)
                    break

    @staticmethod
    def _deck_path_key(deck_path):
        """Normalized form of a deck path, for comparing tabs."""
        if not deck_path:
            return None

        return os.path.normcase(os.path.realpath(os.fspath(deck_path)))

    def find_deck_view_tab(self, deck_path):
        """The open DeckViewTab or None."""
        key = self._deck_path_key(deck_path)

        if key is None:
            return None

        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if isinstance(tab, DeckViewTab) and self._deck_path_key(tab.deck_path) == key:
                return tab

        return None

    def new_deck_view_tab(self, deck_path=None):
        existing = self.find_deck_view_tab(deck_path)
        if existing is not None:
            self.tab_widget.setCurrentWidget(existing)
            return existing

        # Try to create the deck tab
        try:
            deck_tab = DeckViewTab(deck_path=deck_path)
            deck_tab.card_action_requested.connect(self.on_card_action_requested)
            deck_tab.new_canvas_requested.connect(self.new_canvas_from_cards)

            # Close welcome tab if needed
            self.close_welcome_tab()

            self.tab_widget.addTab(deck_tab, "")
            self.tab_widget.setCurrentWidget(deck_tab)

            return deck_tab
        except Exception:
            logger.exception("Error creating deck view tab")
            return None

    def new_library_tab(self, view=None):
        """Create one only if there are none"""
        library_tab = self.find_library_tab()
        if library_tab is None:
            library_tab = LibraryTab()
            self.close_welcome_tab()
            self.tab_widget.addTab(library_tab, "Library")

        if view:
            library_tab.show_view(view)
        self.tab_widget.setCurrentWidget(library_tab)

        return library_tab

    def find_library_tab(self):
        for index in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(index)
            if isinstance(tab, LibraryTab):
                return tab
        return None

    def new_card_view_tab(self):
        self.add_card_tab(CardViewTab())

    def close_tab(self, index):
        # removeTab neither deletes the page nor tells it it has gone
        tab = self.tab_widget.widget(index)
        if isinstance(tab, BaseTab):
            tab.about_to_close()

        if self.tab_widget.count() > 1:  # Keep at least one tab open
            self.tab_widget.removeTab(index)
        else:
            # If it's the last tab, replace it with welcome
            self.tab_widget.removeTab(index)
            self.add_welcome_tab()

    def add_tab_number_shortcuts(self, platform=sys.platform):
        """Alt and a digit picks a tab, or Cmd on macOS"""
        actions = commands.bind(
            self,
            Scope.WINDOW,
            {f"window.tab_{n}": partial(self.select_tab_by_number, n) for n in range(1, 10)},
            platform=platform,
        )
        self.tab_number_actions = list(actions.values())

    def select_tab_by_number(self, number):
        count = self.tab_widget.count()
        index = count - 1 if number == 9 else number - 1
        if 0 <= index < count:
            self.tab_widget.setCurrentIndex(index)

    def close_current_tab(self):
        current_index = self.tab_widget.currentIndex()
        self.close_tab(current_index)

    def open_deck(self):
        """Open a deck by selecting the directory containing deck.toml"""
        file_dialog = QFileDialog()

        # Change to directory selection instead of file selection
        file_dialog.setFileMode(QFileDialog.FileMode.Directory)
        file_dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        file_dialog.setWindowTitle("Select Tarot Deck Directory")

        if file_dialog.exec():
            selected_dirs = file_dialog.selectedFiles()
            if not selected_dirs:
                return

            deck_dir = selected_dirs[0]
            deck_toml_path = os.path.join(deck_dir, "deck.toml")

            # Check if the selected directory contains a deck.toml file
            if not os.path.exists(deck_toml_path):
                QMessageBox.warning(
                    self,
                    "Invalid Deck Directory",
                    "The selected directory does not contain a deck.toml file.\n"
                    "Please select a valid tarot deck directory.",
                )
                return

            # Open the deck
            logger.info(f"Selected deck directory: {deck_dir}")
            self.new_deck_view_tab(deck_path=deck_dir)

    def new_reading(self):
        self.new_canvas_tab()

    def show_preferences(self):
        """Show the preferences dialog"""
        from tarot_canvas.ui.windows.preferences_dialog import PreferencesDialog

        prefs_dialog = PreferencesDialog(self)
        prefs_dialog.settings_changed.connect(self.apply_preferences)
        prefs_dialog.exec()

    def apply_preferences(self):
        """Hand changed preferences to everything that read them only once"""
        self.apply_settings_to_open_canvases()
        self.apply_library_settings()

    def apply_settings_to_open_canvases(self):
        """Re-apply appearance settings to every open canvas tab"""
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if isinstance(tab, CanvasTab):
                tab.apply_background_settings()

    def apply_library_settings(self):
        """The catalog reads the switch once; its entries_changed updates every library"""
        show = get_settings().value(
            SHOW_AVAILABLE_DECKS_KEY, SHOW_AVAILABLE_DECKS_DEFAULT, type=bool
        )
        deck_catalog().set_enabled(bool(show))

    @pyqtSlot(object)
    def on_deck_installed(self, entry):
        self.toast.show_message(DOWNLOAD_TEXT["installed_toast"].format(name=entry.name))

    def on_tab_changed(self, _index):
        # The tab being left keeps whatever it was holding. currentChanged says only
        # where we arrived, so the one we came from is tracked here.
        outgoing, self.previous_tab = self.previous_tab, self.tab_widget.currentWidget()
        if isinstance(outgoing, BaseTab) and outgoing is not self.previous_tab:
            # RuntimeError: the tab we came from is the one that was just closed
            with contextlib.suppress(RuntimeError):
                outgoing.flush_pending_edits()

        if self.fullscreen_tab is not None:
            self.exit_tab_fullscreen()
        self.update_edit_actions()
        self.update_fullscreen_action()
        self.update_zoom_actions()

    # A real slot, so Qt drops the app-wide connection when the window is deleted
    @pyqtSlot()
    @pyqtSlot(int)
    def update_zoom_actions(self, _percent=None):
        """Each action only while the current tab says it would change something"""
        tab = self.current_base_tab()
        for how, action in (
            ("in", self.zoom_in_action),
            ("out", self.zoom_out_action),
            ("reset", self.reset_zoom_action),
        ):
            action.setEnabled(tab is not None and tab.can_zoom(how))

    @pyqtSlot(QWidget, QWidget)
    def on_focus_changed(self, _old, _new):
        self.update_zoom_actions()
        self.update_edit_actions()

    def zoom(self, how):
        tab = self.current_base_tab()
        if tab is not None and tab.can_zoom(how):
            tab.zoom(how)
        self.update_zoom_actions()

    def current_base_tab(self):
        tab = self.tab_widget.currentWidget()
        return tab if isinstance(tab, BaseTab) else None

    @staticmethod
    def edit_args(how):
        return (QGuiApplication.clipboard().mimeData(),) if how == "paste" else ()

    def tab_can_edit(self, how):
        tab = self.current_base_tab()
        return tab is not None and getattr(tab, f"can_{TAB_EDITS[how]}")(*self.edit_args(how))

    # A real slot, so Qt itself drops the clipboard connection when the window is deleted
    @pyqtSlot()
    def update_edit_actions(self):
        """Each Edit entry while the focused text or the current tab would take it"""
        text = focused_text.field()
        for how, action in self.edit_actions.items():
            action.setEnabled(focused_text.can(how, text) or self.tab_can_edit(how))

    def edit(self, how):
        """A focused text field first, then the current tab"""
        text = focused_text.field()
        if focused_text.can(how, text):
            focused_text.run(how, text)
        elif self.tab_can_edit(how):
            getattr(self.current_base_tab(), TAB_EDITS[how])(*self.edit_args(how))
        self.update_edit_actions()

    def find(self):
        tab = self.current_base_tab()
        if tab is not None and tab.can_find():
            tab.find()
        else:
            self.show_command_palette()

    def update_go_actions(self):
        """Go entries enable as the current tab says"""
        tab = self.current_base_tab()
        for where, action in self.go_actions.items():
            action.setEnabled(tab is not None and tab.can_go(where))

    def go(self, where):
        tab = self.current_base_tab()
        if tab is not None and tab.can_go(where):
            tab.go(where)

    def update_fullscreen_action(self):
        tab = self.current_base_tab()
        self.fullscreen_tab_action.setEnabled(
            self.fullscreen_tab is not None or (tab is not None and tab.supports_fullscreen())
        )

    def toggle_tab_fullscreen(self):
        """Toggle a chrome-free fullscreen showing only the current tab"""
        if self.fullscreen_tab is not None:
            self.exit_tab_fullscreen()
            return
        tab = self.tab_widget.currentWidget()
        if isinstance(tab, BaseTab) and tab.supports_fullscreen():
            self.enter_tab_fullscreen(tab)
        else:
            self.fullscreen_tab_action.setChecked(False)

    def enter_tab_fullscreen(self, tab):
        self.fullscreen_tab = tab
        self._pre_fullscreen = {
            "window_fullscreen": self.isFullScreen(),
            "window_maximized": self.isMaximized(),
            "explorer_visible": self.card_explorer.isVisible(),
            "splitter_sizes": self.main_splitter.sizes(),
            "margins": self.centralWidget().layout().contentsMargins(),
            "tab_state": tab.enter_fullscreen(),
        }

        self.menuBar().setVisible(False)
        self.tab_widget.tabBar().setVisible(False)
        self.card_explorer.setVisible(False)
        self.centralWidget().layout().setContentsMargins(0, 0, 0, 0)

        if not self.isFullScreen():
            self.setWindowState(self.windowState() | Qt.WindowState.WindowFullScreen)

        tab.fullscreen_focus_widget().setFocus(Qt.FocusReason.OtherFocusReason)
        self.fullscreen_tab_action.setChecked(True)
        tab.on_fullscreen_changed()

    def exit_tab_fullscreen(self):
        tab = self.fullscreen_tab
        state = self._pre_fullscreen
        self.fullscreen_tab = None
        self._pre_fullscreen = None

        self.menuBar().setVisible(True)
        self.tab_widget.tabBar().setVisible(True)
        if state:
            self.card_explorer.setVisible(state["explorer_visible"])
            self.main_splitter.setSizes(state["splitter_sizes"])
            self.centralWidget().layout().setContentsMargins(state["margins"])
            tab.exit_fullscreen(state["tab_state"])

            # Only undo our own fullscreen
            if not state["window_fullscreen"]:
                window_state = self.windowState() & ~Qt.WindowState.WindowFullScreen
                if state["window_maximized"]:
                    window_state |= Qt.WindowState.WindowMaximized
                self.setWindowState(window_state)

        self.fullscreen_tab_action.setChecked(False)
        tab.on_fullscreen_changed()

    def closeEvent(self, event):
        # Remember the window as it was before any tab took it over
        if self.fullscreen_tab is not None:
            self.exit_tab_fullscreen()
        get_settings().setValue(MAIN_WINDOW_GEOMETRY_KEY, self.saveGeometry())
        super().closeEvent(event)

    def size_splitter_to_explorer(self):
        """Give the explorer its content width only"""
        explorer_width = self.card_explorer.preferred_width()
        total = self.main_splitter.width() or self.width()
        self.main_splitter.setSizes([explorer_width, max(total - explorer_width, 1)])

    def toggle_card_explorer(self, checked):
        """Toggle visibility of the card explorer panel"""
        self.set_card_explorer_visible(checked)

    def set_card_explorer_visible(self, visible):
        """Show or hide the card explorer at the user's request, and remember it"""
        self.apply_card_explorer_visible(visible)
        get_settings().setValue(EXPLORER_VISIBLE_KEY, bool(visible))

    def apply_card_explorer_visible(self, visible):
        """Show or hide the card explorer without touching the stored preference"""
        self.explorer_action.setChecked(visible)
        if visible:
            self.card_explorer.show()
            self.size_splitter_to_explorer()
        else:
            self.card_explorer.hide()
            # Collapse explorer completely
            self.main_splitter.setSizes([0, self.main_splitter.width()])

    def on_explorer_card_selected(self, action, card, deck):
        """Handle card selection from explorer panel (original handler)"""
        # Skip handling if it's a different action than viewing
        if action != "view_card" and action != "use_card":
            return

        # Check if we already have a tab open for this card
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if (
                hasattr(tab, "id")
                and hasattr(tab, "card")
                and tab.card
                and tab.card.get("id") == card.get("id")
            ):
                # Tab exists, just select it
                self.tab_widget.setCurrentWidget(tab)
                return

        # Create a new card view tab
        from tarot_canvas.ui.tabs.card_view_tab import CardViewTab

        card_tab = CardViewTab(card=card, deck=deck)
        self.add_card_tab(card_tab)

    def on_card_action_requested(self, action, card, deck):
        """Handle all card actions from the explorer based on context"""
        current_tab = self.tab_widget.currentWidget()

        if action == "double_click":
            # Check if the current tab is a canvas tab
            if hasattr(current_tab, "id") and current_tab.id.startswith("canvas_"):
                # If it's a canvas tab, add the card to it
                if hasattr(current_tab, "add_specific_card"):
                    current_tab.add_specific_card(card, deck)
                    logger.debug(f"Adding card to canvas: {card['name']}")
            else:
                # For any other tab type, open a card view
                self.open_card_view_tab(card, deck)
                logger.debug(f"Opening card view for: {card['name']}")
        elif action == "use_card":
            # Check if the current tab is a canvas tab
            if hasattr(current_tab, "id") and "canvas_" in current_tab.id:
                # If it's a canvas tab, add the card to it
                if hasattr(current_tab, "add_specific_card"):
                    current_tab.add_specific_card(card, deck)
            else:
                # Default to opening a card view for non-canvas tabs
                self.on_explorer_card_selected("view_card", card, deck)
        elif action == "view_card":
            # Always open the card view for this action
            self.on_explorer_card_selected(action, card, deck)

    def open_card_view_tab(self, card, deck, show_notes=False):
        """Open a tab to view a specific card, or raise the one already open, and return it"""
        # Check if we already have a tab open for this card
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if (
                hasattr(tab, "id")
                and hasattr(tab, "card")
                and tab.card
                and tab.card.get("id") == card.get("id")
            ):
                # Tab exists, just select it
                self.tab_widget.setCurrentWidget(tab)
                if show_notes and hasattr(tab, "show_notes_tab"):
                    tab.show_notes_tab()
                return tab

        # Create a new card view tab
        from tarot_canvas.ui.tabs.card_view_tab import CardViewTab

        card_tab = CardViewTab(card=card, deck=deck, show_notes=show_notes)
        self.add_card_tab(card_tab)
        return card_tab

    def show_faqs(self):
        """Open the FAQ document declared in the metainfo XML"""
        faq = load_about_data().faq
        if faq:
            QDesktopServices.openUrl(QUrl(faq))

    def report_bug(self):
        """Open the bug tracker declared in the metainfo XML"""
        bugtracker = load_about_data().bugtracker
        if bugtracker:
            QDesktopServices.openUrl(QUrl(bugtracker))

    def show_about(self):
        dialog = AboutDialog(self)
        dialog.exec()

    def open_card_view(self, card, deck=None):
        """Open a card view tab for a specific card

        Args:
            card (dict): Card dictionary
            deck (TarotDeck, optional): Deck the card belongs to
        """
        from tarot_canvas.ui.tabs.card_view_tab import CardViewTab

        self.add_card_tab(CardViewTab(card=card, deck=deck))

    def show_log_viewer(self):
        """Show the log viewer dialog"""
        log_viewer = LogViewerDialog(self)
        log_viewer.exec()

    def change_theme(self, theme_type):
        """Change the application theme"""
        logger.info(f"Changing theme to: {theme_type.value}")
        ThemeManager.get_instance().set_theme(theme_type)

    def on_theme_changed(self, theme_name):
        """Handle theme change events"""
        logger.info(f"Theme changed to: {theme_name}")

        # Update checked state of theme actions
        try:
            theme = ThemeType(theme_name)
            for t, action in self.theme_actions.items():
                action.setChecked(t == theme)
        except (ValueError, AttributeError) as e:
            logger.error(f"Error updating theme actions: {e}")

    def open_reference_deck(self):
        """Open the reference deck from the deck manager"""
        # Get reference deck from deck manager
        reference_deck = deck_manager.get_reference_deck()

        if not reference_deck:
            QMessageBox.warning(self, "Deck Not Found", "The reference deck could not be loaded.")
            return

        # Create a deck view tab with the reference deck path
        self.new_deck_view_tab(deck_path=reference_deck.deck_path)
        self.close_welcome_tab()

    def show_command_palette(self):
        """Show the command palette with context-aware behavior"""
        # Determine active tab type
        current_tab = self.tab_widget.currentWidget()
        active_tab_type = ""

        if hasattr(current_tab, "id"):
            if current_tab.id.startswith("canvas_"):
                active_tab_type = "canvas"
            elif hasattr(current_tab, "card"):
                active_tab_type = "card"

        # Create and show command palette
        palette = CommandPalette(self, active_tab_type)
        palette.card_selected.connect(self.handle_command_palette_selection)
        palette.exec()

    def handle_command_palette_selection(self, card, deck):
        """Handle card selection from command palette"""
        # Get active tab
        current_tab = self.tab_widget.currentWidget()

        if hasattr(current_tab, "id") and current_tab.id.startswith("canvas_"):
            # In canvas tab, add card to canvas
            current_tab.add_specific_card(card, deck)
        else:
            # Otherwise, open card view tab
            self.handle_tab_navigation(
                "open_card_view",
                {"card": card, "deck": deck, "source_tab_id": getattr(current_tab, "id", None)},
            )
