from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt

from tarot_canvas.utils import theme_manager
from tarot_canvas.utils.theme_manager import ThemeManager, ThemeType


class FakeStyle:
    def __init__(self, name):
        self.name = name

    def standardPalette(self):
        return "standard"


class FakeHints:
    def __init__(self):
        self.calls = []

    def setColorScheme(self, scheme):
        self.calls.append(("set", scheme))

    def unsetColorScheme(self):
        self.calls.append(("unset",))


class FakeApp:
    """Records what the theme manager asks of the application."""

    def __init__(self):
        self.styles = []
        self.palette = None
        self.stylesheet = None
        self.hints = FakeHints()

    def setStyle(self, style):
        self.styles.append(style.name)

    def style(self):
        return FakeStyle(self.styles[-1])

    def setPalette(self, palette):
        self.palette = palette

    def setStyleSheet(self, stylesheet):
        self.stylesheet = stylesheet

    def styleHints(self):
        return self.hints


@pytest.fixture
def app(monkeypatch):
    fake = FakeApp()
    monkeypatch.setattr(theme_manager, "QApplication", SimpleNamespace(instance=lambda: fake))
    monkeypatch.setattr(theme_manager.QStyleFactory, "create", FakeStyle)
    # _get_system_style asks the host, and the Linux paths must not see a Mac
    monkeypatch.setattr("platform.system", lambda: "Linux")
    # The Flatpak path writes these
    monkeypatch.delenv("QT_STYLE_OVERRIDE", raising=False)
    monkeypatch.delenv("KDEGLOBALS", raising=False)
    return fake


def apply(theme, platform, flatpak=False, styles=("Windows", "Fusion")):
    manager = ThemeManager()
    manager._current_theme = theme
    manager._in_flatpak = flatpak
    manager._available_styles = list(styles)
    manager._apply_theme(platform=platform)


@pytest.mark.parametrize("flatpak", [False, True])
@pytest.mark.parametrize("theme", list(ThemeType))
def test_macos_keeps_the_native_style_under_every_theme(app, theme, flatpak):
    apply(theme, "darwin", flatpak=flatpak, styles=("Breeze", "Fusion"))

    assert app.styles == ["macOS"]
    assert app.palette is None
    assert app.stylesheet == ""


@pytest.mark.parametrize(
    "theme, calls",
    [
        (ThemeType.LIGHT, [("set", Qt.ColorScheme.Light)]),
        (ThemeType.DARK, [("set", Qt.ColorScheme.Dark)]),
        (ThemeType.SYSTEM, [("unset",)]),
    ],
)
def test_macos_themes_choose_only_the_colour_scheme(app, theme, calls):
    apply(theme, "darwin")

    assert app.hints.calls == calls
