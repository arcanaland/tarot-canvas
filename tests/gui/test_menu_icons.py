"""An icon on every menu item, and never the same one twice in a menu (KDE HIG)."""

import os

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QKeySequence

from tarot_canvas.ui.canvas.icons import CanvasIcon
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab


@pytest.fixture(autouse=True)
def breeze(qapp):
    """The names are Breeze's. Offscreen Qt has no platform theme, so no theme and no paths."""
    previous_name, previous_paths = QIcon.themeName(), QIcon.themeSearchPaths()
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    QIcon.setThemeSearchPaths(previous_paths + [f"{d}/icons" for d in data_dirs.split(":") if d])
    QIcon.setThemeName("breeze")
    try:
        if QIcon.fromTheme("document-open").isNull():
            pytest.skip("Breeze isn't installed")
        yield
    finally:
        QIcon.setThemeName(previous_name)
        QIcon.setThemeSearchPaths(previous_paths)


def make_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    with qtbot.waitExposed(window):
        window.show()
    return window


def menus(window):
    """Every menu in the menu bar, submenus included."""

    def walk(menu):
        yield menu
        for action in menu.actions():
            if action.menu():
                yield from walk(action.menu())

    for top in window.menuBar().actions():
        yield from walk(top.menu())


def needs_icon(action):
    """Separators have nothing to show, and in a radio group the mark is the icon."""
    if action.isSeparator():
        return False
    group = action.actionGroup()
    return group is None or not group.isExclusive()


def test_every_menu_item_has_an_icon(qtbot):
    window = make_window(qtbot)

    missing = [
        f"{menu.title()} > {action.text()}"
        for menu in menus(window)
        for action in menu.actions()
        if needs_icon(action) and action.icon().isNull()
    ]

    assert missing == []


def test_the_theme_radio_items_have_no_icon(qtbot):
    window = make_window(qtbot)

    assert all(action.icon().isNull() for action in window.theme_actions.values())


def test_no_two_items_in_a_menu_share_an_icon(qtbot):
    window = make_window(qtbot)

    for menu in menus(window):
        names = [action.icon().name() for action in menu.actions() if needs_icon(action)]
        assert len(names) == len(set(names)), menu.title()


def test_ctrl_p_is_find_card_and_opens_the_finder(qtbot, monkeypatch):
    opened = []
    monkeypatch.setattr(MainWindow, "show_command_palette", lambda self, *_: opened.append(True))
    window = make_window(qtbot)
    go_menu = next(m for m in menus(window) if m.title().replace("&", "") == "Go")

    assert window.find_card_action.shortcut() == QKeySequence("Ctrl+P")
    assert window.find_card_action in go_menu.actions()

    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    qtbot.keyClick(window, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier)
    assert opened == [True]


def test_the_command_palette_is_no_menu_item_of_its_own(qtbot):
    window = make_window(qtbot)

    labels = [a.text().replace("&", "") for menu in menus(window) for a in menu.actions()]

    assert "Command Palette" not in labels


def make_card_view(qtbot, deck):
    tab = CardViewTab(card=deck.get_random_card(), deck=deck)
    qtbot.addWidget(tab)
    return tab


def test_the_card_view_zoom_menu_has_icons(qtbot, minimal_deck):
    bar = make_card_view(qtbot, minimal_deck).card_bar
    actions = [bar.zoom_in_action, bar.zoom_out_action, bar.fit_action, bar.native_action]

    assert not any(action.icon().isNull() for action in actions)
    assert len({action.icon().name() for action in actions}) == len(actions)


def test_the_notes_manage_menu_has_icons(qtbot, minimal_deck):
    button = make_card_view(qtbot, minimal_deck).notes_tab.notes_list_widget.manage_button
    actions = button.menu().actions()

    assert not button.icon().isNull()
    assert not any(action.icon().isNull() for action in actions)
    # Destroying user content takes the red trash can
    delete = next(a for a in actions if a.text() == "Delete Note")
    assert delete.icon().name() == "edit-delete"


def test_a_tab_shows_the_icon_of_the_menu_item_that_opens_it(qtbot):
    window = make_window(qtbot)
    window.new_library_tab()
    tabs = window.tab_widget

    qtbot.waitUntil(lambda: tabs.tabIcon(tabs.currentIndex()).name() == "view-list-icons")
    assert window.new_library_action.icon().name() == "view-list-icons"
    assert window.new_canvas_action.icon().name() == CanvasIcon().name()
