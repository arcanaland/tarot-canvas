from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette

from tarot_canvas.utils import theme_manager
from tarot_canvas.utils.theme_manager import ThemeManager, ThemeType

TOOLTIP_STYLESHEET = """
            QToolTip {
                color: #ffffff;
                background-color: #505050;
                border: 1px solid #777777;
            }
            """


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


def window_colour(palette):
    return palette.color(QPalette.ColorRole.Window).getRgb()[:3]


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


# What main@c7c2137 does on Linux, which RFC-065 must leave exactly as it was:
# (style, Window colour or "standard", stylesheet, or None when it is left alone)
LINUX = {
    (False, True, ThemeType.SYSTEM): ("Breeze", "standard", ""),
    (False, True, ThemeType.LIGHT): ("Breeze", "standard", ""),
    (False, True, ThemeType.DARK): ("Breeze", (53, 53, 53), TOOLTIP_STYLESHEET),
    (False, False, ThemeType.SYSTEM): ("Fusion", "standard", ""),
    (False, False, ThemeType.LIGHT): ("Fusion", "standard", ""),
    (False, False, ThemeType.DARK): ("Fusion", (53, 53, 53), TOOLTIP_STYLESHEET),
    (True, True, ThemeType.SYSTEM): ("Breeze", "standard", ""),
    (True, True, ThemeType.LIGHT): ("Breeze", "standard", ""),
    (True, True, ThemeType.DARK): ("Breeze", (49, 54, 59), None),
    (True, False, ThemeType.SYSTEM): ("Fusion", "standard", ""),
    (True, False, ThemeType.LIGHT): ("Fusion", "standard", ""),
    (True, False, ThemeType.DARK): ("Fusion", (49, 54, 59), None),
}


@pytest.mark.parametrize("flatpak, breeze, theme", list(LINUX))
def test_linux_is_unchanged(app, flatpak, breeze, theme):
    styles = ("Breeze", "Windows", "Fusion") if breeze else ("Windows", "Fusion")
    apply(theme, "linux", flatpak=flatpak, styles=styles)

    style, palette, stylesheet = LINUX[(flatpak, breeze, theme)]
    assert app.styles == [style]
    assert (app.palette if palette == "standard" else window_colour(app.palette)) == palette
    assert app.stylesheet == stylesheet
    assert app.hints.calls == []
