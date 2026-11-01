"""The Breeze subset the Mac draws its icons from."""

import configparser
from pathlib import Path

import pytest
from PyQt6.QtGui import QIcon

from tarot_canvas.utils.theme_manager import ICON_THEMES

THEMES = ("breeze", "breeze-dark")


def files_in(theme):
    root = Path(ICON_THEMES) / theme
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


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
    assert files_in("breeze") == files_in("breeze-dark")
    assert "COPYING-ICONS" in files_in("breeze")


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
