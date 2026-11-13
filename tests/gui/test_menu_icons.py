"""An icon on every menu item, and never the same one twice in a menu (KDE HIG)."""

import os

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QKeySequence
from PyQt6.QtWidgets import QPushButton

from tarot_canvas.settings import LIBRARY_VIEW_DECKS, LIBRARY_VIEW_SPREADS, LIBRARY_VIEWS
from tarot_canvas.ui.canvas.icons import CanvasIcon
from tarot_canvas.ui.icons import LIBRARY_ICON, SPREAD_ICON, deck_icon
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import MAIN_WINDOW, PREFERENCES
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
from tarot_canvas.ui.tabs.spread_tab import SpreadTab
from tarot_canvas.ui.windows.preferences_dialog import PreferencesDialog


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


def drawn(icon):
    """Compares by pixels, because an icon from a file has no theme name"""
    assert not icon.isNull()
    return icon.pixmap(22, 22).toImage()


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
    tab = CardViewTab(card=deck.random_card(), deck=deck)
    qtbot.addWidget(tab)
    return tab


def test_the_card_view_zoom_menu_has_icons(qtbot, minimal_deck):
    bar = make_card_view(qtbot, minimal_deck).card_bar
    actions = [bar.zoom_in_action, bar.zoom_out_action, bar.fit_action, bar.native_action]

    assert not any(action.icon().isNull() for action in actions)
    assert len({action.icon().name() for action in actions}) == len(actions)


def test_the_note_menu_has_icons(qtbot, minimal_deck):
    notes = make_card_view(qtbot, minimal_deck).notes_tab
    actions = notes.note_menu.actions()

    assert not notes.editor_menu_button.icon().isNull()
    assert not any(action.icon().isNull() for action in actions)
    # Destroying user content takes the red trash can
    assert notes.delete_action.icon().name() == "edit-delete"


def test_the_spread_pane_menu_has_icons(qtbot):
    tab = SpreadTab()
    qtbot.addWidget(tab)
    actions = [action for action in tab.pane.menu.actions() if not action.isSeparator()]

    assert not tab.pane.menu_button.icon().isNull()
    assert not any(action.icon().isNull() for action in actions)
    assert len({action.icon().name() for action in actions}) == len(actions)


def test_a_tab_shows_the_icon_of_the_menu_item_that_opens_it(qtbot):
    window = make_window(qtbot)
    window.new_library_tab()
    tabs = window.tab_widget

    qtbot.waitUntil(lambda: tabs.tabIcon(tabs.currentIndex()).name() == LIBRARY_ICON)
    assert window.new_library_action.icon().name() == LIBRARY_ICON
    assert window.new_canvas_action.icon().name() == CanvasIcon().name()


def test_a_new_deck_view_is_labelled_as_it_is_added(qtbot, full_deck):
    window = make_window(qtbot)
    tabs = window.tab_widget

    tab = window.new_deck_view_tab(deck_path=full_deck.root_path)

    index = tabs.indexOf(tab)
    assert tabs.tabText(index) == full_deck.metadata.name
    assert drawn(tabs.tabIcon(index)) == drawn(deck_icon())


def welcome_button(window, text):
    buttons = window.findChildren(QPushButton)
    return next(button for button in buttons if button.text() == text)


def library_of(window):
    window.new_library_tab()
    return window.tab_widget.currentWidget()


def sidebar_row(library, view):
    return library.sidebar.item(LIBRARY_VIEWS.index(view))


def test_the_library_has_one_icon(qtbot):
    window = make_window(qtbot)
    expected = drawn(QIcon.fromTheme(LIBRARY_ICON))

    assert drawn(window.new_library_action.icon()) == expected
    assert drawn(library_of(window).tab_icon()) == expected
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    rows = [dialog.page_list.item(row) for row in range(dialog.page_list.count())]
    library_row = next(row for row in rows if row.text() == PREFERENCES["library"])
    assert drawn(library_row.icon()) == expected


def test_a_deck_has_one_icon_and_it_is_not_a_neighbours(qtbot, full_deck):
    window = make_window(qtbot)
    expected = drawn(deck_icon())

    assert drawn(welcome_button(window, MAIN_WINDOW["welcome_open_deck"]).icon()) == expected
    tab = window.new_deck_view_tab(deck_path=full_deck.root_path)
    assert drawn(tab.tab_icon()) == expected
    assert drawn(sidebar_row(library_of(window), LIBRARY_VIEW_DECKS).icon()) == expected
    assert expected != drawn(QIcon.fromTheme(SPREAD_ICON))
    assert expected != drawn(QIcon.fromTheme(LIBRARY_ICON))


def test_a_spread_has_one_icon(qtbot):
    window = make_window(qtbot)
    expected = drawn(QIcon.fromTheme(SPREAD_ICON))

    assert drawn(window.new_spread_action.icon()) == expected
    canvas = window.new_canvas_tab()
    assert drawn(canvas.commands["canvas.save_layout_as_spread"].icon()) == expected
    assert drawn(sidebar_row(library_of(window), LIBRARY_VIEW_SPREADS).icon()) == expected
    assert drawn(SpreadTab().tab_icon()) == expected


# No surface shows an icon for these: a tab has no fixed one, the wheel and Esc are shown nowhere,
# and the card view's info tabs have none
NO_ICON_ANYWHERE = {
    *(f"window.tab_{n}" for n in range(1, 10)),
    *(f"card.view_{n}" for n in range(1, 4)),
    "canvas.turn",
    "canvas.turn_fine",
    "canvas.cancel",
    "card.cancel",
}


def test_every_shortcut_shows_the_icon_it_has_elsewhere(qtbot):
    from tarot_canvas.ui.windows.shortcuts_page import COMMAND_ROLE

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    model = dialog.shortcuts_page.model
    blank, shown = set(), set()
    for group_row in range(model.rowCount()):
        group = model.index(group_row, 0)
        for row in range(model.rowCount(group)):
            item = model.itemFromIndex(model.index(row, 0, group))
            command_id = item.data(COMMAND_ROLE)
            (blank if item.icon().isNull() else shown).add(command_id)
    assert blank == NO_ICON_ANYWHERE


def test_a_card_image_key_wears_the_icon_of_the_go_entry_showing_it(qapp):
    from tarot_canvas.ui.commands import command_icon

    for art, entry in [
        ("card_image.previous_or_pan", "window.go_previous"),
        ("card_image.previous", "window.go_previous"),
        ("card_image.next", "window.go_next"),
        ("card_image.random", "window.go_random"),
        ("card_image.next_deck", "window.go_next_deck"),
    ]:
        assert drawn(command_icon(art)) == drawn(command_icon(entry)), art


def test_a_library_view_key_wears_its_sidebar_row_s_icon(qtbot):
    from tarot_canvas.ui.commands import command_icon
    from tarot_canvas.ui.library.tab import LibraryTab

    tab = LibraryTab()
    qtbot.addWidget(tab)
    for n, view in enumerate(LIBRARY_VIEWS, 1):
        row = tab.sidebar.item(n - 1)
        assert drawn(command_icon(f"library.view_{n}")) == drawn(row.icon()), view
