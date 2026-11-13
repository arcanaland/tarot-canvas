"""The Breeze subset the Mac draws its icons from."""

import configparser
from pathlib import Path

import pytest
from PyQt6.QtGui import QIcon

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
