import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWIDGETSIZE_MAX, QApplication, QTabWidget, QToolButton

from tarot_canvas.settings import EXPLORER_VISIBLE_KEY, get_settings
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.library_tab import LibraryTab
from tests.conftest import MINIMAL_DECK_PATH


@pytest.fixture(autouse=True)
def no_stored_explorer_visibility():
    """Qt resolves the QSettings path once per process, so the file outlives a test."""
    get_settings().remove(EXPLORER_VISIBLE_KEY)
    yield
    get_settings().remove(EXPLORER_VISIBLE_KEY)


def test_main_window_opens_with_welcome_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    tab_widget = window.findChild(QTabWidget)
    assert tab_widget is not None
    assert tab_widget.count() >= 1
    assert tab_widget.tabText(0) == "Welcome"


def make_window_with_canvas(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    tab = window.new_canvas_tab()
    return window, tab


def test_canvas_fullscreen_hides_chrome_and_puts_it_back(qtbot):
    window, tab = make_window_with_canvas(qtbot)
    explorer_before = window.card_explorer.isVisible()

    tab.on_toggle_fullscreen()
    assert window.fullscreen_tab is tab
    assert not window.menuBar().isVisible()
    assert not window.tab_widget.tabBar().isVisible()
    assert not window.card_explorer.isVisible()
    assert tab.fullscreen_action.isChecked()

    tab.on_escape_pressed()
    assert window.fullscreen_tab is None
    assert window.menuBar().isVisible()
    assert window.tab_widget.tabBar().isVisible()
    assert window.card_explorer.isVisible() == explorer_before
    assert not tab.fullscreen_action.isChecked()
    assert not window.fullscreen_tab_action.isChecked()


def test_the_canvas_grows_with_the_window(qtbot):
    """No height cap: a maximized window must not leave a gap under the canvas."""
    window, tab = make_window_with_canvas(qtbot)
    window.resize(1200, 1400)
    qtbot.waitUntil(lambda: tab.height() > 900)

    assert tab.maximumHeight() == QWIDGETSIZE_MAX


def test_escape_still_clears_the_selection_when_not_fullscreen(qtbot):
    window, tab = make_window_with_canvas(qtbot)
    tab.scene.addRect(0, 0, 10, 10).setSelected(True)

    tab.on_escape_pressed()
    assert tab.scene.selectedItems() == []
    assert window.fullscreen_tab is None


def test_switching_tabs_leaves_canvas_fullscreen(qtbot):
    window, tab = make_window_with_canvas(qtbot)
    other = window.new_canvas_tab()
    window.tab_widget.setCurrentWidget(tab)

    tab.on_toggle_fullscreen()
    assert window.fullscreen_tab is tab

    window.tab_widget.setCurrentWidget(other)
    assert window.fullscreen_tab is None
    assert window.menuBar().isVisible()


def test_a_standalone_canvas_tab_ignores_fullscreen(qtbot):
    tab = CanvasTab()
    qtbot.addWidget(tab)

    tab.on_toggle_fullscreen()  # no main window to hide chrome on
    assert not tab.is_fullscreen()


def test_the_f_key_drives_it_from_the_canvas(qtbot):
    window, tab = make_window_with_canvas(qtbot)
    window.activateWindow()
    qtbot.waitActive(window)
    tab.view.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is tab.view)

    qtbot.keyClick(tab.view, Qt.Key.Key_F)
    assert window.fullscreen_tab is tab

    qtbot.keyClick(tab.view, Qt.Key.Key_Escape)
    assert window.fullscreen_tab is None


def test_f11_fullscreens_the_canvas_from_anywhere_in_the_window(qtbot):
    window, tab = make_window_with_canvas(qtbot)
    window.activateWindow()
    qtbot.waitActive(window)
    # F11 is window-scope, so send it somewhere that is not the canvas
    window.card_explorer.setFocus()
    qtbot.waitUntil(lambda: window.isActiveWindow())

    qtbot.keyClick(window, Qt.Key.Key_F11)
    assert window.fullscreen_tab is tab

    qtbot.keyClick(window, Qt.Key.Key_F11)
    assert window.fullscreen_tab is None
    assert window.menuBar().isVisible()


def test_f11_on_a_tab_that_opts_out_does_nothing(qtbot):
    window, tab = make_window_with_canvas(qtbot)
    # new_canvas_tab() closes the Welcome tab, so put a non-canvas tab back
    window.add_welcome_tab()
    window.tab_widget.setCurrentIndex(window.tab_widget.count() - 1)
    assert not isinstance(window.tab_widget.currentWidget(), CanvasTab)

    window.toggle_tab_fullscreen()
    assert window.fullscreen_tab is None
    assert window.menuBar().isVisible()
    assert not window.fullscreen_tab_action.isChecked()


def test_the_library_tab_opts_out_of_fullscreen(qtbot):
    """Capability, not isinstance: a tab is fullscreened only if it says so."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.new_library_tab()

    assert not window.tab_widget.currentWidget().supports_fullscreen()
    window.toggle_tab_fullscreen()
    assert window.fullscreen_tab is None


def make_window_with_card_view(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.new_card_view_tab()
    return window, window.tab_widget.currentWidget()


def test_card_view_fullscreen_shows_the_artwork_alone(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    # the switcher hides itself when only one deck has the card; force it on so
    # there is something for fullscreen to collapse and restore
    tab.deck_switcher.setVisible(True)
    sizes_before = tab.splitter.sizes()

    window.toggle_tab_fullscreen()
    assert window.fullscreen_tab is tab
    assert not window.menuBar().isVisible()
    assert not tab.deck_switcher.isVisibleTo(tab)
    assert tab.splitter.sizes()[1] == 0  # info pane collapsed

    window.toggle_tab_fullscreen()
    assert window.fullscreen_tab is None
    assert window.menuBar().isVisible()
    assert tab.deck_switcher.isVisibleTo(tab)
    assert tab.splitter.sizes() == sizes_before


def test_escape_leaves_card_view_fullscreen(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    window.toggle_tab_fullscreen()

    tab.on_escape_pressed()
    assert window.fullscreen_tab is None


def test_escape_still_resets_the_zoom_when_not_fullscreen(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    view = tab.image_view
    view.zoom_to(4.0 * view.native_scale())

    tab.on_escape_pressed()
    assert view.is_at_fit()
    assert window.fullscreen_tab is None


def test_ctrl_shift_f_fullscreens_the_current_tab(qtbot):
    """The KDE standard shortcut, and the one the HIG wants on a laptop."""
    window, tab = make_window_with_card_view(qtbot)
    window.activateWindow()
    qtbot.waitUntil(lambda: window.isActiveWindow())

    qtbot.keyClick(
        window,
        Qt.Key.Key_F,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert window.fullscreen_tab is tab

    qtbot.keyClick(
        window,
        Qt.Key.Key_F,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert window.fullscreen_tab is None


def test_nothing_overlays_the_artwork_until_fullscreen(qtbot):
    """Windowed, the card owns the pane: no button, no toast on top of it."""
    window, tab = make_window_with_card_view(qtbot)

    assert not tab.exit_fullscreen_button.isVisible()
    assert not tab.toast.isVisible()
    assert window.fullscreen_tab is None


def test_fullscreen_offers_a_button_and_a_hint_at_the_key(qtbot):
    window, tab = make_window_with_card_view(qtbot)

    window.toggle_tab_fullscreen()
    assert tab.exit_fullscreen_button.isVisible()
    assert tab.toast.isVisible()
    assert "Esc" in tab.toast.text()
    # the hint must sit beside the card, never over the artwork it interrupts
    image = tab.image_view.image_viewport_rect()
    qtbot.waitUntil(lambda: not tab.toast.geometry().intersects(image))

    # the button is the way out for anyone who does not read the hint
    qtbot.mouseClick(tab.exit_fullscreen_button, Qt.MouseButton.LeftButton)
    assert window.fullscreen_tab is None
    assert not tab.exit_fullscreen_button.isVisible()
    # the hint described a mode that is over; it must not linger over the layout
    assert not tab.toast.isVisible()


def test_the_hint_fades_on_its_own(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    window.toggle_tab_fullscreen()

    tab.toast.show_message("Press Esc to exit fullscreen", hold_ms=10)
    qtbot.waitUntil(lambda: not tab.toast.isVisible(), timeout=3000)
    assert window.fullscreen_tab is tab  # fading the hint changes nothing else


def test_the_exit_button_tracks_the_top_corner_of_the_image_view(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    view, button = tab.image_view, tab.exit_fullscreen_button
    window.toggle_tab_fullscreen()
    qtbot.waitUntil(lambda: view.width() > 100)

    def in_the_top_trailing_corner():
        margin = button.MARGIN
        return (
            button.geometry().right() == view.width() - margin - 1
            and button.geometry().top() == margin
        )

    qtbot.waitUntil(in_the_top_trailing_corner)
    window.resize(1100, 800)
    qtbot.waitUntil(in_the_top_trailing_corner)


def test_switching_tabs_leaves_card_view_fullscreen(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    tab.deck_switcher.setVisible(True)
    other = window.new_canvas_tab()
    window.tab_widget.setCurrentWidget(tab)
    window.toggle_tab_fullscreen()
    assert window.fullscreen_tab is tab

    window.tab_widget.setCurrentWidget(other)
    assert window.fullscreen_tab is None
    assert tab.deck_switcher.isVisibleTo(tab)


def test_the_explorer_is_open_on_a_first_launch(qtbot):
    window = make_shown_window(qtbot)
    assert window.card_explorer.isVisible()
    assert window.explorer_action.isChecked()


def test_the_explorer_close_button_hides_it(qtbot):
    window = make_shown_window(qtbot)

    window.card_explorer.close_button.click()

    assert not window.card_explorer.isVisible()
    assert not window.explorer_action.isChecked()
    assert not get_settings().value(EXPLORER_VISIBLE_KEY, True, type=bool)


def test_a_closed_explorer_stays_closed_next_session(qtbot):
    first = make_shown_window(qtbot)
    first.card_explorer.close_button.click()

    second = make_shown_window(qtbot)
    assert not second.card_explorer.isVisible()
    assert not second.explorer_action.isChecked()

    second.explorer_action.trigger()
    assert second.card_explorer.isVisible()

    third = make_shown_window(qtbot)
    assert third.card_explorer.isVisible()
    assert third.explorer_action.isChecked()


def test_opening_the_same_deck_twice_reuses_its_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    first = window.new_deck_view_tab(deck_path=str(MINIMAL_DECK_PATH))
    count_after_first = window.tab_widget.count()
    window.new_canvas_tab()
    window.tab_widget.setCurrentIndex(window.tab_widget.count() - 1)

    second = window.new_deck_view_tab(deck_path=str(MINIMAL_DECK_PATH))

    assert second is first
    assert window.tab_widget.count() == count_after_first + 1  # only the canvas tab
    assert window.tab_widget.currentWidget() is first


def test_the_same_deck_reached_by_a_path_object_reuses_its_tab(qtbot):
    """The reference deck is a Path for some reason."""
    window = MainWindow()
    qtbot.addWidget(window)

    first = window.new_deck_view_tab(deck_path=str(MINIMAL_DECK_PATH))
    second = window.new_deck_view_tab(deck_path=MINIMAL_DECK_PATH)

    assert second is first


def test_a_deck_link_from_a_card_view_reuses_the_open_deck_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    first = window.new_deck_view_tab(deck_path=str(MINIMAL_DECK_PATH))
    count_before = window.tab_widget.count()
    window.new_canvas_tab()
    window.tab_widget.setCurrentIndex(window.tab_widget.count() - 1)

    window.handle_tab_navigation("open_deck_view", {"deck_path": str(MINIMAL_DECK_PATH)})

    assert window.tab_widget.count() == count_before + 1
    assert window.tab_widget.currentWidget() is first


def make_shown_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def middle_click(qtbot, tab_bar, index, release_index=None):
    """Press and release the middle button over tabs."""
    press = tab_bar.tabRect(index).center()
    release = tab_bar.tabRect(index if release_index is None else release_index).center()
    qtbot.mousePress(tab_bar, Qt.MouseButton.MiddleButton, pos=press)
    qtbot.mouseRelease(tab_bar, Qt.MouseButton.MiddleButton, pos=release)


def test_middle_click_closes_exactly_one_tab(qtbot):
    window = make_shown_window(qtbot)
    for _ in range(4):
        window.new_canvas_tab()
    tab_bar = window.tab_widget.tabBar()
    count_before = window.tab_widget.count()
    doomed = window.tab_widget.widget(1)
    survivor = window.tab_widget.widget(2)

    middle_click(qtbot, tab_bar, 1)

    assert window.tab_widget.count() == count_before - 1
    assert window.tab_widget.indexOf(doomed) == -1
    assert window.tab_widget.indexOf(survivor) != -1


def file_menu(window):
    return window.menuBar().actions()[0].menu()


def test_opening_a_tab_takes_no_drill_down(qtbot):
    """The New submenu is gone: three items did not earn a level of navigation."""
    window = MainWindow()
    qtbot.addWidget(window)
    actions = file_menu(window).actions()
    assert not any(action.menu() for action in actions), "File has no submenus"

    labels = [action.text() for action in actions if not action.isSeparator()]
    assert labels[:3] == ["New &Canvas", "New &Library View", "New C&ard View"]


def test_the_new_tab_shortcuts_survived_the_flattening(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    shortcuts = {
        action.text(): action.shortcut().toString() for action in file_menu(window).actions()
    }
    assert shortcuts["New &Library View"] == "Ctrl+L"
    assert shortcuts["New &Canvas"] == "Ctrl+N"
    assert shortcuts["New C&ard View"] == "Ctrl+T"


def test_the_tab_bar_has_a_new_tab_button(qtbot):
    """What every tabbed app has: one click for the default tab, an arrow for the rest."""
    window = MainWindow()
    qtbot.addWidget(window)
    corner = window.tab_widget.cornerWidget(Qt.Corner.TopRightCorner)
    buttons = corner.findChildren(QToolButton)
    new_tab = next(b for b in buttons if b.menu() is not None)

    assert new_tab.defaultAction() is window.new_canvas_action
    assert new_tab.popupMode() == QToolButton.ToolButtonPopupMode.MenuButtonPopup
    assert new_tab.menu().actions() == [
        window.new_canvas_action,
        window.new_library_action,
        window.new_card_view_action,
    ]


def test_the_new_tab_button_actually_opens_a_tab(qtbot):
    """The button's default action is the shared QAction, so triggering it is the click."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_canvas_action.trigger()
    # The new-tab helpers close the Welcome tab as they open, so the count is unchanged.
    assert isinstance(window.tab_widget.currentWidget(), CanvasTab)

    window.new_library_action.trigger()
    assert isinstance(window.tab_widget.currentWidget(), LibraryTab)


def test_the_search_button_is_still_reachable(qtbot):
    """It shared the corner with nothing before; now it shares a container."""
    window = MainWindow()
    qtbot.addWidget(window)
    corner = window.tab_widget.cornerWidget(Qt.Corner.TopRightCorner)
    assert len(corner.findChildren(QToolButton)) == 2


def help_menu(window):
    return next(
        action.menu()
        for action in window.menuBar().actions()
        if action.text().replace("&", "") == "Help"
    )


def test_help_menu_offers_a_path_to_the_bug_tracker(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    labels = [action.text().replace("&", "") for action in help_menu(window).actions()]

    assert labels == [
        "Frequently Asked Questions",
        "Report Bug",
        "",  # separator
        "About Tarot Canvas",
    ]


def test_the_faq_url_also_comes_from_the_metainfo(qtbot, monkeypatch):
    from tarot_canvas.about import load_about_data
    from tarot_canvas.ui import main_window as main_window_module

    opened = []
    monkeypatch.setattr(
        main_window_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window.show_faqs()

    assert opened == [load_about_data().faq]
