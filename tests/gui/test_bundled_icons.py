"""The Breeze subset the Mac draws its icons from."""

import configparser
from pathlib import Path

import pytest
from PyQt6.QtGui import QColor, QIcon

from tarot_canvas.ui.tabs.card_view.notes_list import EMPTY_ICON
from tarot_canvas.ui.widgets.placeholder_message import ICON_SIZE, tint_icon
from tarot_canvas.utils.theme_manager import ICON_THEMES

THEMES = ("breeze", "breeze-dark")


def icons_in(theme):
    root = Path(ICON_THEMES) / theme
    return sorted(str(p.relative_to(root)) for p in root.rglob("*.svg"))


@pytest.mark.parametrize("theme", THEMES)
def test_the_index_declares_every_directory_it_lists(theme):
    index = configparser.ConfigParser(interpolation=None)
    index.read(Path(ICON_THEMES) / theme / "index.theme")

    directories = index["Icon Theme"]["Directories"].split(",")
    assert directories
    for directory in directories:
        assert (Path(ICON_THEMES) / theme / directory).is_dir()
        assert index[directory]["Size"] == directory.split("/")[1]


def test_light_and_dark_hold_the_same_icons():
    assert icons_in("breeze")
    assert icons_in("breeze") == icons_in("breeze-dark")


@pytest.mark.parametrize("theme", THEMES)
def test_each_set_carries_the_lgpl_and_the_gpl_it_amends(theme):
    root = Path(ICON_THEMES) / theme
    assert "GNU Lesser General Public" in (root / "COPYING-ICONS").read_text()
    assert (root / "GPL-3.0-or-later.txt").read_text().startswith("GNU GENERAL PUBLIC LICENSE")


def test_only_the_recoloured_set_says_it_was_modified():
    assert not (Path(ICON_THEMES) / "breeze" / "NOTICE").exists()
    assert "modified" in (Path(ICON_THEMES) / "breeze-dark" / "NOTICE").read_text()


@pytest.fixture
def icon_theme(qapp):
    paths, name = QIcon.themeSearchPaths(), QIcon.themeName()
    yield
    QIcon.setThemeSearchPaths(paths)
    QIcon.setThemeName(name)


@pytest.mark.parametrize("theme", THEMES)
def test_qt_finds_an_icon_no_platform_table_has(icon_theme, theme):
    QIcon.setThemeSearchPaths([ICON_THEMES])
    QIcon.setThemeName(theme)

    assert not QIcon.fromTheme("sidebar-expand-right").isNull()


def drawn_extent(icon, side):
    """How many pixels across the opaque part of the icon spans when painted at side"""
    image = tint_icon(icon, side, 1.0, QColor("black"))
    columns = [
        x
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha()
    ]
    return max(columns) - min(columns) + 1


@pytest.mark.parametrize("theme", THEMES)
def test_an_empty_state_icon_fills_its_slot(icon_theme, theme):
    """Qt doesn't scale a Fixed directory past its size, so a 96 px slot drew a 22 px glyph"""
    QIcon.setThemeSearchPaths([ICON_THEMES])
    QIcon.setThemeName(theme)
    icon = QIcon.fromTheme(EMPTY_ICON)

    assert drawn_extent(icon, ICON_SIZE) > ICON_SIZE // 2
    assert drawn_extent(icon, 16) <= 16
