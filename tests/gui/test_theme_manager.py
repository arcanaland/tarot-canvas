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


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in self.slots:
            slot(*args)


class FakeHints:
    def __init__(self):
        self.calls = []
        self.scheme = Qt.ColorScheme.Light  # what the OS says
        self.colorSchemeChanged = FakeSignal()

    def setColorScheme(self, scheme):
        self.calls.append(("set", scheme))

    def unsetColorScheme(self):
        self.calls.append(("unset",))

    def colorScheme(self):
        return self.scheme


class FakeIcon:
    """Qt's icon theme is process-wide, so the tests must not touch the real one."""

    def __init__(self):
        self.theme_name = ""
        self.search_paths = [":/icons"]
        self.calls = []

    def themeSearchPaths(self):
        return list(self.search_paths)

    def setThemeSearchPaths(self, paths):
        self.calls.append("setThemeSearchPaths")
        self.search_paths = list(paths)

    def setThemeName(self, name):
        self.calls.append("setThemeName")
        self.theme_name = name


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
    fake.icons = FakeIcon()
    monkeypatch.setattr(theme_manager, "QApplication", SimpleNamespace(instance=lambda: fake))
    monkeypatch.setattr(theme_manager, "QIcon", fake.icons)
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
    return manager


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


@pytest.mark.parametrize(
    "theme, os_scheme, icons",
    [
        (ThemeType.LIGHT, Qt.ColorScheme.Dark, "breeze"),
        (ThemeType.DARK, Qt.ColorScheme.Light, "breeze-dark"),
        (ThemeType.SYSTEM, Qt.ColorScheme.Light, "breeze"),
        (ThemeType.SYSTEM, Qt.ColorScheme.Dark, "breeze-dark"),
        (ThemeType.SYSTEM, Qt.ColorScheme.Unknown, "breeze"),
    ],
)
def test_macos_draws_breeze_in_the_scheme_on_screen(app, theme, os_scheme, icons):
    app.hints.scheme = os_scheme
    apply(theme, "darwin")

    assert app.icons.theme_name == icons
    assert app.icons.search_paths == [theme_manager.ICON_THEMES, ":/icons"]


def test_macos_system_icons_follow_the_os_live(app):
    apply(ThemeType.SYSTEM, "darwin")

    app.hints.colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert app.icons.theme_name == "breeze-dark"
    app.hints.colorSchemeChanged.emit(Qt.ColorScheme.Light)
    assert app.icons.theme_name == "breeze"


def test_macos_light_and_dark_icons_ignore_the_os(app):
    manager = apply(ThemeType.DARK, "darwin")
    app.hints.colorSchemeChanged.emit(Qt.ColorScheme.Light)
    assert app.icons.theme_name == "breeze-dark"

    manager._current_theme = ThemeType.LIGHT
    manager._apply_theme(platform="darwin")
    app.hints.colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    assert app.icons.theme_name == "breeze"


def test_macos_reapplying_registers_the_bundle_once(app):
    manager = apply(ThemeType.SYSTEM, "darwin")
    for theme in (ThemeType.DARK, ThemeType.LIGHT, ThemeType.SYSTEM):
        manager._current_theme = theme
        manager._apply_theme(platform="darwin")

    assert app.icons.search_paths == [theme_manager.ICON_THEMES, ":/icons"]
    assert len(app.hints.colorSchemeChanged.slots) == 1
