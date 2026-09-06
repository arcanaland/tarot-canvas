import shutil

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QTabWidget

from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tests.conftest import MINIMAL_DECK_PATH


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
    max_height_before = tab.maximumHeight()

    tab.on_toggle_fullscreen()
    assert window.canvas_fullscreen_tab is tab
    assert not window.menuBar().isVisible()
    assert not window.tab_widget.tabBar().isVisible()
    assert not window.card_explorer.isVisible()
    assert tab.maximumHeight() > max_height_before
    assert tab.fullscreen_action.isChecked()

    tab.on_escape_pressed()
    assert window.canvas_fullscreen_tab is None
    assert window.menuBar().isVisible()
    assert window.tab_widget.tabBar().isVisible()
    assert window.card_explorer.isVisible() == explorer_before
    assert tab.maximumHeight() == max_height_before
    assert not tab.fullscreen_action.isChecked()
    assert not window.fullscreen_canvas_action.isChecked()


def test_escape_still_clears_the_selection_when_not_fullscreen(qtbot):
    window, tab = make_window_with_canvas(qtbot)
    tab.scene.addRect(0, 0, 10, 10).setSelected(True)

    tab.on_escape_pressed()
    assert tab.scene.selectedItems() == []
    assert window.canvas_fullscreen_tab is None


def test_switching_tabs_leaves_canvas_fullscreen(qtbot):
    window, tab = make_window_with_canvas(qtbot)
    other = window.new_canvas_tab()
    window.tab_widget.setCurrentWidget(tab)

    tab.on_toggle_fullscreen()
    assert window.canvas_fullscreen_tab is tab

    window.tab_widget.setCurrentWidget(other)
    assert window.canvas_fullscreen_tab is None
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
    assert window.canvas_fullscreen_tab is tab

    qtbot.keyClick(tab.view, Qt.Key.Key_Escape)
    assert window.canvas_fullscreen_tab is None


def test_f11_fullscreens_the_canvas_from_anywhere_in_the_window(qtbot):
    window, tab = make_window_with_canvas(qtbot)
    window.activateWindow()
    qtbot.waitActive(window)
    # F11 is window-scope, so send it somewhere that is not the canvas
    window.card_explorer.setFocus()
    qtbot.waitUntil(lambda: window.isActiveWindow())

    qtbot.keyClick(window, Qt.Key.Key_F11)
    assert window.canvas_fullscreen_tab is tab

    qtbot.keyClick(window, Qt.Key.Key_F11)
    assert window.canvas_fullscreen_tab is None
    assert window.menuBar().isVisible()


def test_f11_on_a_non_canvas_tab_does_nothing(qtbot):
    window, tab = make_window_with_canvas(qtbot)
    # new_canvas_tab() closes the Welcome tab, so put a non-canvas tab back
    window.add_welcome_tab()
    window.tab_widget.setCurrentIndex(window.tab_widget.count() - 1)
    assert not isinstance(window.tab_widget.currentWidget(), CanvasTab)

    window.toggle_canvas_fullscreen()
    assert window.canvas_fullscreen_tab is None
    assert window.menuBar().isVisible()
    assert not window.fullscreen_canvas_action.isChecked()


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
