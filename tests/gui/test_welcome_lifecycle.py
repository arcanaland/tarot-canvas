import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QMessageBox, QTabBar

from tarot_canvas.settings import SHOW_WELCOME_KEY, get_settings, get_show_welcome
from tarot_canvas.ui.library.tab import LibraryTab
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.welcome_tab import WelcomeTab
from tarot_canvas.ui.windows.preferences_dialog import PreferencesDialog


@pytest.fixture(autouse=True)
def discard_on_teardown(monkeypatch):
    monkeypatch.setattr(
        "tarot_canvas.ui.main_window.QMessageBox.warning",
        lambda *_: QMessageBox.StandardButton.Discard,
    )


@pytest.fixture
def make_window(qtbot, stub_deck_manager, spreads_base):
    def make():
        window = MainWindow()
        qtbot.addWidget(window)
        return window

    return make


def kinds(window):
    return [type(window.tab_widget.widget(i)) for i in range(window.tab_widget.count())]


def close_button(window, index):
    tab_bar = window.tab_widget.tabBar()
    sides = (QTabBar.ButtonPosition.RightSide, QTabBar.ButtonPosition.LeftSide)
    return next(b for side in sides if (b := tab_bar.tabButton(index, side)) is not None)


def test_the_window_opens_on_the_welcome_tab_alone(make_window):
    assert kinds(make_window()) == [WelcomeTab]


def test_with_the_welcome_tab_turned_off_the_window_opens_on_the_library(make_window):
    get_settings().setValue(SHOW_WELCOME_KEY, False)

    assert kinds(make_window()) == [LibraryTab]


def test_closing_the_welcome_tab_alone_lands_on_the_library(make_window):
    window = make_window()
    welcome = window.tab_widget.widget(0)

    assert window.close_tab(0)

    assert kinds(window) == [LibraryTab]
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(welcome)


def test_closing_the_last_tab_lands_on_the_library(make_window):
    window = make_window()
    canvas = window.new_canvas_tab()

    window.close_tab(window.tab_widget.indexOf(canvas))

    assert kinds(window) == [LibraryTab]


def test_the_library_alone_cannot_be_closed(make_window):
    window = make_window()
    window.close_tab(0)

    _, close = window.tab_context_menu(0).actions()
    assert not close.isEnabled()
    assert not window.close_tab(0)
    window.close_current_tab()
    assert kinds(window) == [LibraryTab]
    assert close_button(window, 0).isHidden()


def test_the_library_beside_another_tab_closes_like_any_other(make_window):
    window = make_window()
    window.close_tab(0)
    window.new_canvas_tab()

    assert not close_button(window, 0).isHidden()
    _, close = window.tab_context_menu(0).actions()
    assert close.isEnabled()
    assert window.close_tab(0)
    assert kinds(window) == [CanvasTab]


def test_help_welcome_brings_it_back_once_and_raises_it(make_window):
    window = make_window()
    canvas = window.new_canvas_tab()
    assert WelcomeTab not in kinds(window)

    window.show_welcome_tab()
    welcome = window.tab_widget.currentWidget()
    assert isinstance(welcome, WelcomeTab)

    window.tab_widget.setCurrentWidget(canvas)
    window.show_welcome_tab()
    assert window.tab_widget.currentWidget() is welcome
    assert kinds(window).count(WelcomeTab) == 1


def test_the_footer_checkbox_is_the_setting(make_window):
    welcome = make_window().tab_widget.widget(0)
    assert welcome.show_at_startup.isChecked()

    welcome.show_at_startup.setChecked(False)

    assert not get_show_welcome()


def test_preferences_and_the_footer_follow_each_other(qtbot, make_window):
    welcome = make_window().tab_widget.widget(0)
    welcome.show_at_startup.setChecked(False)

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert not dialog.show_welcome_check.isChecked()

    dialog.show_welcome_check.setChecked(True)
    dialog.apply_settings()

    assert get_show_welcome()
    assert welcome.show_at_startup.isChecked()
