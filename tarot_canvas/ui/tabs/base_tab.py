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

    def supports_fullscreen(self):
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
        """The widget that should hold keyboard focus while fullscreen."""
        return self

    def request_fullscreen_toggle(self):
        window = self.window()
        if self.supports_fullscreen() and hasattr(window, "toggle_tab_fullscreen"):
            window.toggle_tab_fullscreen()

    # -- card clipboard --------------------------------------------------
    # Edit > Copy Card / Paste Card

    def can_copy_card(self):
        return False

    def copy_card(self):
        """Put this tab's card on the clipboard."""

    def can_paste_card(self, mime):
        return False

    def paste_card(self, mime):
        """Place the card mime carries."""

    # -- go ----------------------------------------------------------------
    # The Go menu asks the current tab. where is one of previous, next, first,
    # last, random, previous_deck, next_deck; the keys are the tab's own.

    def can_go(self, where):
        return False

    def go(self, where):
        """Show another card in this tab."""
