import logging

import pytest
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import QApplication, QPushButton

from tarot_canvas.settings import (
    LEGACY_THEME_KEY,
    LEGACY_THEME_STORE,
    THEME_KEY,
    get_settings,
    get_theme,
)
from tarot_canvas.ui import colour_scheme
from tarot_canvas.ui.colour_scheme import palette_from_scheme
from tarot_canvas.utils import theme_manager
from tarot_canvas.utils.theme_manager import SCHEME_PATH_PROPERTY, ThemeManager, ThemeType

Role = QPalette.ColorRole
Group = QPalette.ColorGroup


def colours(palette):
    """Every role's colour in every group"""
    return {
        (group, role): palette.color(group, role).rgba()
        for group in (Group.Active, Group.Inactive, Group.Disabled)
        for role in Role
        if role not in (Role.NColorRoles, Role.NoRole)
    }


def window_lightness():
    return QApplication.instance().palette().color(Role.Window).lightness()


@pytest.fixture
def startup(qapp):
    """The palette and icon theme the app had before any theme, put back afterwards"""
    before = QPalette(qapp.palette())
    icon_paths, icon_theme = QIcon.themeSearchPaths(), QIcon.themeName()
    yield before
    qapp.setProperty(SCHEME_PATH_PROPERTY, None)
    qapp.setPalette(QPalette())
    qapp.styleHints().unsetColorScheme()
    # Last: on the Mac path, a scheme change sets the icon theme
    QIcon.setThemeSearchPaths(icon_paths)
    QIcon.setThemeName(icon_theme)


@pytest.fixture
def manager(startup):
    manager = ThemeManager()
    manager.apply_at_startup()
    return manager


def apply(manager, theme, platform="linux"):
    manager._current_theme = theme
    manager._apply_theme(platform=platform)


def test_light_is_light_and_dark_is_dark(manager):
    apply(manager, ThemeType.LIGHT)
    light = window_lightness()
    apply(manager, ThemeType.DARK)
    dark = window_lightness()

    assert light > 128 > dark


def test_the_scheme_reaches_the_menu_bar_and_title_bar(manager, colour_schemes):
    app = QApplication.instance()

    apply(manager, ThemeType.LIGHT)
    assert app.property(SCHEME_PATH_PROPERTY) == str(colour_schemes / colour_scheme.LIGHT_SCHEME)

    apply(manager, ThemeType.SYSTEM)
    assert app.property(SCHEME_PATH_PROPERTY) is None


@pytest.mark.parametrize(
    "first, second", [(ThemeType.LIGHT, ThemeType.DARK), (ThemeType.SYSTEM, ThemeType.LIGHT)]
)
def test_a_switch_makes_the_style_anew(manager, first, second):
    """So Breeze re-reads the scheme for the menu bar; offscreen has no Breeze to show it"""
    apply(manager, first)
    # By name, not identity: the new style may reuse the old one's address and wrapper
    QApplication.style().setObjectName("before")

    apply(manager, second)

    assert QApplication.style().objectName() != "before"
    assert QApplication.style().name() == manager._startup_style


def test_the_card_explorer_header_follows_the_theme(qtbot, manager):
    from PyQt6.QtWidgets import QLabel

    from tarot_canvas.ui.components.card_explorer import CardExplorerPanel

    apply(manager, ThemeType.DARK)
    explorer = CardExplorerPanel()
    qtbot.addWidget(explorer)
    explorer.show()  # a stylesheet pins the palette when it polishes, on show
    header = next(
        label for label in explorer.findChildren(QLabel) if label.text() == "Card Explorer"
    )

    apply(manager, ThemeType.LIGHT)
    qtbot.waitUntil(lambda: header.palette().color(Role.WindowText).lightness() < 128)


def test_system_after_light_is_the_startup_palette(manager, startup):
    apply(manager, ThemeType.LIGHT)
    apply(manager, ThemeType.SYSTEM)

    assert colours(QApplication.instance().palette()) == colours(startup)


def test_a_new_widget_takes_the_theme(qtbot, manager):
    apply(manager, ThemeType.DARK)
    button = QPushButton()
    qtbot.addWidget(button)

    assert button.palette().color(Role.Button).lightness() < 128


@pytest.mark.parametrize("theme", [ThemeType.LIGHT, ThemeType.DARK])
def test_a_missing_scheme_follows_the_system_and_says_so(
    manager, startup, theme, tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(colour_scheme, "SCHEME_DIR", tmp_path)
    caplog.set_level(logging.WARNING)

    apply(manager, theme)

    assert colours(QApplication.instance().palette()) == colours(startup)
    assert str(tmp_path) in caplog.text


@pytest.mark.parametrize("theme", list(ThemeType))
def test_the_mac_reads_no_scheme_and_sets_no_palette(manager, startup, theme, monkeypatch):
    def unread(path):
        raise AssertionError(f"read {path}")

    monkeypatch.setattr(colour_scheme, "palette_from_scheme", unread)
    # The macOS style doesn't exist here; handing back the current one leaves the style be
    monkeypatch.setattr(theme_manager.QStyleFactory, "create", lambda name: QApplication.style())

    apply(manager, theme, platform="darwin")

    assert colours(QApplication.instance().palette()) == colours(startup)


@pytest.mark.parametrize("theme", list(ThemeType))
def test_linux_leaves_the_icon_theme_alone(manager, colour_schemes, theme):
    paths, name = QIcon.themeSearchPaths(), QIcon.themeName()

    apply(manager, theme)

    assert QIcon.themeSearchPaths() == paths
    assert QIcon.themeName() == name


def test_a_scheme_sets_its_roles(colour_schemes, qapp):
    palette = palette_from_scheme(colour_schemes / colour_scheme.LIGHT_SCHEME)

    assert palette.color(Role.Window).getRgb()[:3] == (239, 240, 241)
    assert palette.color(Role.Base).getRgb()[:3] == (255, 255, 255)
    assert palette.color(Role.Highlight).getRgb()[:3] == (61, 174, 233)
    assert palette.color(Role.ToolTipText).getRgb()[:3] == (35, 38, 41)
    assert palette.color(Role.PlaceholderText).getRgb()[:3] == (112, 125, 138)


@pytest.mark.parametrize("scheme", [colour_scheme.LIGHT_SCHEME, colour_scheme.DARK_SCHEME])
def test_disabled_text_fades_towards_its_background(colour_schemes, qapp, scheme):
    palette = palette_from_scheme(colour_schemes / scheme)

    for role, background in ((Role.ButtonText, Role.Button), (Role.WindowText, Role.Window)):
        active = palette.color(Group.Active, role)
        disabled = palette.color(Group.Disabled, role)
        ground = palette.color(Group.Disabled, background).lightness()
        assert disabled != active
        assert abs(disabled.lightness() - ground) < abs(active.lightness() - ground)


def test_inactive_is_active(colour_schemes, qapp):
    palette = palette_from_scheme(colour_schemes / colour_scheme.DARK_SCHEME)

    assert all(
        palette.color(Group.Inactive, role) == palette.color(Group.Active, role)
        for role, _, _ in colour_scheme.ROLES
    )


def test_the_theme_moves_once_from_its_old_store():
    from PyQt6.QtCore import QSettings

    legacy = QSettings(*LEGACY_THEME_STORE)
    legacy.setValue(LEGACY_THEME_KEY, "dark")

    assert get_theme() == "dark"
    assert get_settings().value(THEME_KEY) == "dark"
    assert not legacy.contains(LEGACY_THEME_KEY)


def test_the_new_store_wins_over_the_old():
    from PyQt6.QtCore import QSettings

    legacy = QSettings(*LEGACY_THEME_STORE)
    legacy.setValue(LEGACY_THEME_KEY, "dark")
    get_settings().setValue(THEME_KEY, "light")

    assert get_theme() == "light"
    legacy.remove(LEGACY_THEME_KEY)


def test_set_theme_stores_it_with_every_other_setting(manager):
    manager.set_theme(ThemeType.DARK)

    assert get_settings().value(THEME_KEY) == "dark"


def test_the_log_viewer_follows_the_palette_whatever_the_theme(qtbot, manager):
    from tarot_canvas.ui.windows.log_viewer import LogViewerDialog

    apply(manager, ThemeType.LIGHT)
    viewer = LogViewerDialog()
    qtbot.addWidget(viewer)
    assert viewer.LOG_COLORS is LogViewerDialog.LIGHT_THEME_COLORS

    # Qt posts the palette change to each widget
    apply(manager, ThemeType.DARK)
    qtbot.waitUntil(lambda: viewer.LOG_COLORS is LogViewerDialog.DARK_THEME_COLORS)
