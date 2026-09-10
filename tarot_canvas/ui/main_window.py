import os
from importlib.resources import files
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QKeySequence,
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
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.about import load_about_data
from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.settings import EXPLORER_VISIBLE_DEFAULT, EXPLORER_VISIBLE_KEY, get_settings
from tarot_canvas.ui.command_palette import CommandPalette
from tarot_canvas.ui.components.card_explorer import CardExplorerPanel
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab
from tarot_canvas.ui.tabs.library_tab import LibraryTab
from tarot_canvas.ui.windows.about import AboutDialog
from tarot_canvas.ui.windows.log_viewer import LogViewerDialog
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.theme_manager import ThemeManager, ThemeType

ICON_PATH = files("tarot_canvas.resources.icons").joinpath("icon.png")


class TabBarEventFilter(QObject):
    rename_tab_requested = pyqtSignal(int)  # Signal with tab index
    close_tab_requested = pyqtSignal(int)  # Signal with tab index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._middle_press_index = -1

    def eventFilter(self, obj, event):
        """Filter events for the tab bar"""
        tab_bar = obj
        if event.type() == QEvent.Type.MouseButtonDblClick:
            # Get the tab index that was double-clicked
            for i in range(tab_bar.count()):
                if tab_bar.tabRect(i).contains(event.pos()):
                    # Check if we have a canvas tab at this index
                    tab_widget = tab_bar.parent()
                    tab = tab_widget.widget(i)
                    if hasattr(tab, "id") and tab.id.startswith("canvas_"):
                        self.rename_tab_requested.emit(i)
                    break
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

        # The tab currently fullscreened, and the chrome state to put back
        self.fullscreen_tab = None
        self._pre_fullscreen = None

        # Initialize theme manager
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.on_theme_changed)

        # Apply current theme
        self.theme_manager._apply_theme()

        self.create_menus()
        self.init_ui()

        QGuiApplication.clipboard().dataChanged.connect(self.update_card_clipboard_actions)
        self.update_card_clipboard_actions()

    def create_menus(self):
        # Create menu bar
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")

        # New Buttons
        self.new_canvas_action = QAction("New &Canvas", self)
        self.new_canvas_action.setShortcut("Ctrl+N")
        self.new_canvas_action.setIcon(QIcon.fromTheme("document-new"))
        self.new_canvas_action.triggered.connect(self.new_canvas_tab)
        file_menu.addAction(self.new_canvas_action)

        self.new_library_action = QAction("New &Library View", self)
        self.new_library_action.setShortcut("Ctrl+L")
        self.new_library_action.setIcon(QIcon.fromTheme("view-list-icons"))
        self.new_library_action.triggered.connect(self.new_library_tab)
        file_menu.addAction(self.new_library_action)

        self.new_card_view_action = QAction("New C&ard View", self)
        self.new_card_view_action.setShortcut("Ctrl+T")
        self.new_card_view_action.setIcon(QIcon.fromTheme("card"))
        self.new_card_view_action.triggered.connect(self.new_card_view_tab)
        file_menu.addAction(self.new_card_view_action)

        file_menu.addSeparator()

        open_action = QAction("&Open Deck", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_deck)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        close_tab_action = QAction("Close &Tab", self)
        close_tab_action.setShortcut("Ctrl+W")
        close_tab_action.triggered.connect(self.close_current_tab)
        file_menu.addAction(close_tab_action)

        file_menu.addSeparator()

        exit_action = QAction("&Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menu_bar.addMenu("&Edit")
        edit_menu.aboutToShow.connect(self.update_card_clipboard_actions)

        # The only bindings of Ctrl+C / Ctrl+V in the app: the current tab answers.
        # On the window too, or hiding the menu bar in fullscreen kills the keys.
        self.copy_card_action = QAction("&Copy Card", self)
        self.copy_card_action.setShortcuts(QKeySequence.StandardKey.Copy)
        self.copy_card_action.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_card_action.triggered.connect(self.copy_card)
        edit_menu.addAction(self.copy_card_action)
        self.addAction(self.copy_card_action)

        self.paste_card_action = QAction("&Paste Card", self)
        self.paste_card_action.setShortcuts(QKeySequence.StandardKey.Paste)
        self.paste_card_action.setIcon(QIcon.fromTheme("edit-paste"))
        self.paste_card_action.triggered.connect(self.paste_card)
        edit_menu.addAction(self.paste_card_action)
        self.addAction(self.paste_card_action)

        edit_menu.addSeparator()

        preferences_action = QAction("&Preferences", self)
        preferences_action.triggered.connect(self.show_preferences)
        edit_menu.addAction(preferences_action)

        # View menu
        view_menu = menu_bar.addMenu("&View")

        # Add explorer toggle to View menu
        self.explorer_action = QAction("&Card Explorer", self)
        self.explorer_action.setShortcut("Ctrl+E")
        self.explorer_action.setCheckable(True)
        self.explorer_action.setChecked(True)  # Set checked by default
        self.explorer_action.triggered.connect(self.toggle_card_explorer)
        view_menu.addAction(self.explorer_action)

        view_menu.addSeparator()

        self.fullscreen_tab_action = QAction("&Fullscreen", self)
        self.fullscreen_tab_action.setShortcuts([QKeySequence("Ctrl+Shift+F"), QKeySequence("F11")])
        self.fullscreen_tab_action.setStatusTip("Fullscreen the current tab (Ctrl+Shift+F or F)")
        self.fullscreen_tab_action.setCheckable(True)
        self.fullscreen_tab_action.triggered.connect(self.toggle_tab_fullscreen)
        view_menu.addAction(self.fullscreen_tab_action)
        self.addAction(self.fullscreen_tab_action)

        # Add Theme submenu
        theme_menu = QMenu("&Theme", self)
        view_menu.addMenu(theme_menu)

        # Create a theme action group for radio behavior
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

        # Tools menu
        tools_menu = menu_bar.addMenu("&Tools")

        # Add Command Palette action
        command_palette_action = QAction("&Command Palette", self)
        command_palette_action.setShortcut("Ctrl+P")
        command_palette_action.triggered.connect(self.show_command_palette)
        tools_menu.addAction(command_palette_action)
        # The one binding of Ctrl+P; on the window too, so fullscreen keeps it
        self.addAction(command_palette_action)

        # Add Log Viewer action
        log_viewer_action = QAction("&Log Viewer", self)
        log_viewer_action.triggered.connect(self.show_log_viewer)
        tools_menu.addAction(log_viewer_action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")

        faq_action = QAction("&Frequently Asked Questions", self)
        faq_action.triggered.connect(self.show_faqs)
        help_menu.addAction(faq_action)

        report_bug_action = QAction("&Report Bug", self)
        report_bug_action.triggered.connect(self.report_bug)
        help_menu.addAction(report_bug_action)

        help_menu.addSeparator()

        about_action = QAction("&About Tarot Canvas", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def init_ui(self):
        # Create main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(2)

        # Create splitter for explorer panel and tab area
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

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
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)

        self.tab_bar_filter = TabBarEventFilter(self)
        self.tab_widget.tabBar().installEventFilter(self.tab_bar_filter)
        self.tab_bar_filter.rename_tab_requested.connect(self.show_tab_rename_dialog)
        self.tab_bar_filter.close_tab_requested.connect(self.close_tab)

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
        new_tab_button.setToolTip("New tab (Ctrl+N)")

        new_tab_menu = QMenu(new_tab_button)
        new_tab_menu.addAction(self.new_canvas_action)
        new_tab_menu.addAction(self.new_library_action)
        new_tab_menu.addAction(self.new_card_view_action)
        new_tab_button.setMenu(new_tab_menu)

        # Create search button and put it in the tab corner
        search_button = QToolButton()
        search_button.setIcon(
            QIcon.fromTheme(
                "search",
                QIcon(str(Path(__file__).parent.parent / "resources" / "icons" / "search.png")),
            )
        )
        search_button.setToolTip("Search Cards (Ctrl+P)")
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
        canvas_btn = QPushButton("New Canvas")
        canvas_btn.clicked.connect(self.new_canvas_tab)
        button_layout.addWidget(canvas_btn)

        deck_btn = QPushButton("Open Standard Deck")
        deck_btn.clicked.connect(self.open_reference_deck)
        button_layout.addWidget(deck_btn)

        library_btn = QPushButton("Deck Library")
        library_btn.clicked.connect(self.new_library_tab)
        button_layout.addWidget(library_btn)

        card_btn = QPushButton("Pick Random Card")
        card_btn.clicked.connect(self.new_card_view_tab)
        button_layout.addWidget(card_btn)

        layout.addLayout(button_layout)
        welcome_tab.setLayout(layout)

        self.tab_widget.addTab(welcome_tab, "Welcome")

    def close_welcome_tab(self):
        """Close the welcome tab if it exists"""
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Welcome":
                self.tab_widget.removeTab(i)
                break

    def new_canvas_tab(self):
        canvas_tab = CanvasTab()
        canvas_tab.navigation_requested.connect(self.handle_tab_navigation)
        self.close_welcome_tab()
        tab_index = self.tab_widget.addTab(canvas_tab, "Canvas")
        self.tab_widget.setCurrentWidget(canvas_tab)

        # Set up double-click event filter for tab renaming
        self.setup_tab_renaming(tab_index, canvas_tab)

        return canvas_tab

    def setup_tab_renaming(self, tab_index, tab):
        """Set up double-click renaming for a tab (currently only for Canvas tabs)"""
        if not hasattr(tab, "id") or not tab.id.startswith("canvas_"):
            return  # Only apply to canvas tabs

        # Store initial tab name for reference
        tab.original_tab_name = self.tab_widget.tabText(tab_index)

    def show_tab_rename_dialog(self, tab_index):
        """Show a dialog to rename the tab at the given index"""
        tab = self.tab_widget.widget(tab_index)
        if not tab or not hasattr(tab, "id") or not tab.id.startswith("canvas_"):
            return  # Only canvas tabs are renamable

        current_name = self.tab_widget.tabText(tab_index)
        new_name, ok = QInputDialog.getText(
            self, "Rename Canvas", "Enter a new name for this canvas:", text=current_name
        )

        if ok and new_name:
            # Update the tab text
            self.tab_widget.setTabText(tab_index, new_name)

            # Also store the name in the tab object
            tab.tab_name = new_name

    def add_card_tab(self, card_tab, title, close_welcome=False):
        """Adopt a card view tab. Every construction site must come through here."""
        card_tab.navigation_requested.connect(self.handle_tab_navigation)
        if close_welcome:
            self.close_welcome_tab()
        self.tab_widget.addTab(card_tab, title)
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
            self.add_card_tab(card_tab, card.get("name", "Card"))

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

            # Close welcome tab if needed
            self.close_welcome_tab()

            # Add tab with initial title
            initial_title = "Deck View"
            if deck_path:
                initial_title = os.path.basename(deck_path)

            tab_index = self.tab_widget.addTab(deck_tab, initial_title)

            # Set current to this tab
            self.tab_widget.setCurrentWidget(deck_tab)

            # Immediately try to update the title if we have a deck loaded
            if deck_path and hasattr(deck_tab, "deck") and deck_tab.deck:
                pretty_name = deck_tab.deck.get_name()
                self.tab_widget.setTabText(tab_index, pretty_name)

            # Still connect the signal for future updates
            deck_tab.title_changed.connect(
                lambda new_title: self.tab_widget.setTabText(
                    self.tab_widget.indexOf(deck_tab), new_title
                )
            )

            return deck_tab
        except Exception:
            logger.exception("Error creating deck view tab")
            return None

    def new_library_tab(self):
        library_tab = LibraryTab()
        self.close_welcome_tab()
        self.tab_widget.addTab(library_tab, "Library")
        self.tab_widget.setCurrentWidget(library_tab)

    def new_card_view_tab(self):
        self.add_card_tab(CardViewTab(), "Card View", close_welcome=True)

    def close_tab(self, index):
        if self.tab_widget.count() > 1:  # Keep at least one tab open
            self.tab_widget.removeTab(index)
        else:
            # If it's the last tab, replace it with welcome
            self.tab_widget.removeTab(index)
            self.add_welcome_tab()

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
        prefs_dialog.settings_changed.connect(self.apply_settings_to_open_canvases)
        prefs_dialog.exec()

    def apply_settings_to_open_canvases(self):
        """Re-apply appearance settings to every open canvas tab"""
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if isinstance(tab, CanvasTab):
                tab.apply_background_settings()

    def on_tab_changed(self, _index):
        if self.fullscreen_tab is not None:
            self.exit_tab_fullscreen()
        self.update_card_clipboard_actions()

    def current_base_tab(self):
        tab = self.tab_widget.currentWidget()
        return tab if isinstance(tab, BaseTab) else None

    # A real slot, so Qt itself drops the clipboard connection when the window is deleted
    @pyqtSlot()
    def update_card_clipboard_actions(self):
        """Copy/Paste Card enable as the current tab says, for what is on the clipboard"""
        tab = self.current_base_tab()
        mime = QGuiApplication.clipboard().mimeData()
        self.copy_card_action.setEnabled(tab is not None and tab.can_copy_card())
        self.paste_card_action.setEnabled(tab is not None and tab.can_paste_card(mime))

    def copy_card(self):
        tab = self.current_base_tab()
        if tab is not None and tab.can_copy_card():
            tab.copy_card()

    def paste_card(self):
        tab = self.current_base_tab()
        mime = QGuiApplication.clipboard().mimeData()
        if tab is not None and tab.can_paste_card(mime):
            tab.paste_card(mime)
        self.update_card_clipboard_actions()

    def toggle_tab_fullscreen(self):
        """Toggle a chrome-free fullscreen showing only the current tab

        Which tabs may be fullscreened is the tab's own answer
        (BaseTab.supports_fullscreen), not a type check here.
        """
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
        self.add_card_tab(card_tab, card.get("name", "Card"))

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

    def open_card_view_tab(self, card, deck):
        """Open a new tab to view a specific card"""
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
        self.add_card_tab(card_tab, card.get("name", "Card"))

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

        self.add_card_tab(CardViewTab(card=card, deck=deck), card["name"])

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
