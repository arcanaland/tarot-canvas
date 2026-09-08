from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class BaseTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

    def set_placeholder(self, text):
        """Helper to show placeholder text in empty tabs"""
        placeholder = QLabel(text)
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(placeholder)

    # -- fullscreen ------------------------------------------------------
    #
    # The main window owns the chrome-free mode (menu bar, tab bar, explorer,
    # margins); a tab opts in here and collapses whatever chrome of its own it
    # wants gone. Tabs that do not override supports_fullscreen() are simply
    # never fullscreened, rather than being swept in by a type check.

    def supports_fullscreen(self):
        """Whether this tab is worth showing chrome-free."""
        return False

    def enter_fullscreen(self):
        """Collapse the tab's own chrome. Returns state for exit_fullscreen."""
        return None

    def exit_fullscreen(self, state):
        """Put back whatever enter_fullscreen collapsed."""

    def is_fullscreen(self):
        """True when the main window is currently fullscreened onto this tab"""
        return getattr(self.window(), "fullscreen_tab", None) is self

    def on_fullscreen_changed(self):
        """Hook for keeping a tab-side affordance in step with the state."""

    def fullscreen_focus_widget(self):
        """The widget that should hold keyboard focus while fullscreen.

        Fullscreen is usually entered from the menu or from the explorer, so
        focus is outside the tab -- and the tab's shortcuts are scoped to it
        (WidgetWithChildrenShortcut), so Esc and the bare letters would do
        nothing until the user clicked into the tab. Tabs name the widget whose
        scope those shortcuts live in.
        """
        return self

    def request_fullscreen_toggle(self):
        """Ask the main window to toggle fullscreen onto this tab.

        The tab asks its window rather than emitting a signal wired up at
        creation time, so this works from every place a tab gets constructed,
        and is a no-op for a tab that has no main window.
        """
        window = self.window()
        if self.supports_fullscreen() and hasattr(window, "toggle_tab_fullscreen"):
            window.toggle_tab_fullscreen()
