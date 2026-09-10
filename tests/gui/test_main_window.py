import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWIDGETSIZE_MAX, QApplication, QTabWidget, QToolButton

from tarot_canvas.settings import EXPLORER_VISIBLE_KEY, get_settings
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.card_transfer import CARD_MIME
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab
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


def test_leaving_fullscreen_puts_a_maximized_window_back_as_maximized(qtbot):
    window, tab = make_window_with_canvas(qtbot)
    window.showMaximized()
    qtbot.waitUntil(window.isMaximized)

    tab.on_toggle_fullscreen()
    assert window.isFullScreen()

    tab.on_escape_pressed()
    qtbot.waitUntil(window.isMaximized)
    assert not window.isFullScreen()


def test_the_canvas_grows_with_the_window(qtbot):
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
    assert tab.card_bar.isVisibleTo(tab)
    sizes_before = tab.splitter.sizes()

    window.toggle_tab_fullscreen()
    assert window.fullscreen_tab is tab
    assert not window.menuBar().isVisible()
    assert not tab.card_bar.isVisibleTo(tab)
    assert not tab.bar_seam.isVisibleTo(tab)
    assert tab.splitter.sizes()[1] == 0  # info pane collapsed

    window.toggle_tab_fullscreen()
    assert window.fullscreen_tab is None
    assert window.menuBar().isVisible()
    assert tab.card_bar.isVisibleTo(tab)
    assert tab.bar_seam.isVisibleTo(tab)
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

    # the button is the way out for anyone who does not read the hint
    qtbot.mouseClick(tab.exit_fullscreen_button, Qt.MouseButton.LeftButton)
    assert window.fullscreen_tab is None
    assert not tab.exit_fullscreen_button.isVisible()
    # the hint described a mode that is over; it must not linger over the layout
    assert not tab.toast.isVisible()


def test_fullscreen_offers_a_way_back_to_the_card_details(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    width_before = tab.splitter.sizes()[1]
    assert width_before > 0

    window.toggle_tab_fullscreen()
    assert tab.info_pane_button.isVisible()
    assert not tab.info_pane_is_open()
    assert "Show card details" in tab.info_pane_button.toolTip()
    assert "Esc" in tab.toast.text()

    qtbot.mouseClick(tab.info_pane_button, Qt.MouseButton.LeftButton)
    assert tab.info_pane_is_open()
    assert tab.splitter.sizes()[1] == width_before
    assert "Hide card details" in tab.info_pane_button.toolTip()

    qtbot.mouseClick(tab.info_pane_button, Qt.MouseButton.LeftButton)
    assert not tab.info_pane_is_open()


def test_the_i_key_toggles_the_card_details(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    window.toggle_tab_fullscreen()
    tab.image_view.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is tab.image_view)

    qtbot.keyClick(tab.image_view, Qt.Key.Key_I)
    assert tab.info_pane_is_open()

    qtbot.keyClick(tab.image_view, Qt.Key.Key_I)
    assert not tab.info_pane_is_open()


def test_dragging_the_pane_open_updates_the_button(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    window.toggle_tab_fullscreen()
    total = sum(tab.splitter.sizes())

    tab.splitter.setSizes([total - 300, 300])
    tab.splitter.splitterMoved.emit(total - 300, 1)
    assert "Hide card details" in tab.info_pane_button.toolTip()


def test_the_fullscreen_tabs_share_the_pane_between_them(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    bar = tab.info_tabs.tabBar()
    windowed = bar.width()

    window.toggle_tab_fullscreen()
    tab.toggle_info_pane()
    qtbot.waitUntil(lambda: bar.width() > windowed)

    widths = [bar.tabRect(i).width() for i in range(bar.count())]
    assert sum(widths) >= bar.width() - 4  # they fill it
    assert max(widths) - min(widths) <= 2  # in equal shares


def test_a_seam_marks_off_the_info_pane(qtbot):
    """Something for the splitter handle to sit against, so it reads as one."""
    window, tab = make_window_with_card_view(qtbot)
    assert tab.pane_seam.width() > 0

    # and it collapses with the pane rather than leaving a stray line
    window.toggle_tab_fullscreen()
    qtbot.waitUntil(lambda: tab.pane_seam.width() == 0)


def test_switching_tabs_leaves_card_view_fullscreen(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    other = window.new_canvas_tab()
    window.tab_widget.setCurrentWidget(tab)
    window.toggle_tab_fullscreen()
    assert window.fullscreen_tab is tab

    window.tab_widget.setCurrentWidget(other)
    assert window.fullscreen_tab is None
    assert tab.card_bar.isVisibleTo(tab)
    qtbot.wait(1100)  # the canvas's startup timers


def test_the_bar_fullscreen_button_tracks_the_state(qtbot):
    window, tab = make_window_with_card_view(qtbot)
    action = tab.card_bar.fullscreen_action

    action.trigger()
    assert window.fullscreen_tab is tab
    assert action.isChecked()

    tab.on_escape_pressed()
    assert window.fullscreen_tab is None
    assert not action.isChecked()


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


def deck_link(tab):
    """The href behind the Deck: value in the overview pane."""
    return tab.overview_tab.deck_value.text().split("'")[1]


@pytest.mark.parametrize(
    "open_a_card",
    [
        pytest.param(lambda w, card, deck: w.new_card_view_tab(), id="File > New Card View"),
        pytest.param(lambda w, card, deck: w.open_card_view(card, deck), id="open_card_view"),
        pytest.param(
            lambda w, card, deck: w.handle_tab_navigation(
                "open_card_view", {"card": card, "deck": deck}
            ),
            id="navigation request",
        ),
    ],
)
def test_the_deck_link_opens_the_deck_however_the_card_was_opened(
    qtbot, open_a_card, stub_deck_manager
):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    deck = stub_deck_manager.get_reference_deck()
    open_a_card(window, deck.get_random_card(), deck)
    tab = window.tab_widget.currentWidget()

    tab.overview_tab.on_deck_link_clicked(deck_link(tab))

    assert isinstance(window.tab_widget.currentWidget(), DeckViewTab)


# -- card clipboard ------------------------------------------------------------


def edit_menu(window):
    return next(
        action.menu()
        for action in window.menuBar().actions()
        if action.text().replace("&", "") == "Edit"
    )


@pytest.fixture
def other_deck(tmp_path, stub_deck_manager, minimal_deck):
    """A second installed deck with the same cards, to tell the copied deck apart."""
    import shutil

    from tarot_canvas.models.deck import TarotDeck

    shutil.copytree(MINIMAL_DECK_PATH, tmp_path / "other")
    deck = TarotDeck(str(tmp_path / "other"))
    stub_deck_manager.get_all_decks = lambda: [minimal_deck, deck]
    return deck


def activate(qtbot, window, widget):
    """Shortcuts only fire in the active window, at whatever has focus."""
    window.activateWindow()
    qtbot.waitActive(window)
    widget.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is widget)


def ctrl(qtbot, widget, key):
    qtbot.keyClick(widget, key, Qt.KeyboardModifier.ControlModifier)


def test_the_edit_menu_lists_copy_and_paste(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    labels = [action.text().replace("&", "") for action in edit_menu(window).actions()]

    assert labels == ["Copy Card", "Paste Card", "", "Preferences"]
    assert window.copy_card_action.shortcut().toString() == "Ctrl+C"
    assert window.paste_card_action.shortcut().toString() == "Ctrl+V"


def test_ctrl_c_and_ctrl_v_are_bound_exactly_once(qtbot):
    """Two bindings of one key make Qt fire neither; that is the Ctrl+P bug."""
    from PyQt6.QtGui import QAction, QKeySequence, QShortcut

    window, card_view = make_window_with_card_view(qtbot)
    window.new_canvas_tab()

    for key in ("Ctrl+C", "Ctrl+V"):
        sequence = QKeySequence(key)
        bound = [a for a in window.findChildren(QAction) if sequence in a.shortcuts()]
        bound += [s for s in window.findChildren(QShortcut) if s.key() == sequence]
        assert len(bound) == 1, key
    qtbot.wait(1100)


def test_copy_card_is_offered_by_a_card_view_and_not_a_canvas(qtbot):
    window, card_view = make_window_with_card_view(qtbot)
    assert window.copy_card_action.isEnabled()

    window.new_canvas_tab()
    assert not window.copy_card_action.isEnabled()

    window.tab_widget.setCurrentWidget(card_view)
    assert window.copy_card_action.isEnabled()
    qtbot.wait(1100)


def test_a_card_copied_in_one_deck_is_pasted_from_that_deck(qtbot, clipboard, other_deck):
    window = make_shown_window(qtbot)
    window.open_card_view(other_deck.get_card_by_id("major_arcana.01"), other_deck)
    window.copy_card_action.trigger()

    canvas = window.new_canvas_tab()
    assert window.paste_card_action.isEnabled()
    window.paste_card_action.trigger()

    cards = [item for item in canvas.scene.items() if isinstance(item, DraggableCardItem)]
    assert len(cards) == 1
    assert cards[0].card_data["id"] == "major_arcana.01"
    assert cards[0].card_data["image"].startswith(str(other_deck.deck_path))
    qtbot.wait(1100)


def test_paste_waits_for_a_card_on_the_clipboard(qtbot, clipboard):
    window, canvas = make_window_with_canvas(qtbot)
    assert not window.paste_card_action.isEnabled()
    assert not canvas.paste_action.isEnabled()

    clipboard.setText("just some text")
    assert not window.paste_card_action.isEnabled()

    window.open_card_view(canvas.deck.get_random_card(), canvas.deck)
    window.copy_card_action.trigger()
    assert not window.paste_card_action.isEnabled(), "a card view has nowhere to paste"

    window.tab_widget.setCurrentWidget(canvas)
    assert window.paste_card_action.isEnabled()
    assert canvas.paste_action.isEnabled()
    qtbot.wait(1100)


def test_ctrl_c_copies_the_card_and_ctrl_v_places_it(qtbot, clipboard):
    window, card_view = make_window_with_card_view(qtbot)
    activate(qtbot, window, card_view.image_view)
    ctrl(qtbot, card_view.image_view, Qt.Key.Key_C)
    assert clipboard.mimeData().hasFormat(CARD_MIME)

    canvas = window.new_canvas_tab()
    activate(qtbot, window, canvas.view)
    ctrl(qtbot, canvas.view, Qt.Key.Key_V)

    cards = [item for item in canvas.scene.items() if isinstance(item, DraggableCardItem)]
    assert [c.card_data["id"] for c in cards] == [card_view.card["id"]]
    assert not window.paste_card_action.isEnabled(), "one paste per copy"

    ctrl(qtbot, canvas.view, Qt.Key.Key_V)
    cards = [item for item in canvas.scene.items() if isinstance(item, DraggableCardItem)]
    assert len(cards) == 1
    qtbot.wait(1100)


def test_one_paste_per_canvas_per_copy(qtbot, clipboard):
    window, card_view = make_window_with_card_view(qtbot)
    window.copy_card_action.trigger()
    first = window.new_canvas_tab()
    window.paste_card_action.trigger()
    assert not window.paste_card_action.isEnabled()

    window.new_canvas_tab()
    assert window.paste_card_action.isEnabled(), "another canvas has not had it yet"

    window.tab_widget.setCurrentWidget(first)
    assert not window.paste_card_action.isEnabled()
    qtbot.wait(1100)


def test_ctrl_c_still_copies_in_fullscreen(qtbot, clipboard):
    """The menu bar is hidden there, which would take its shortcuts with it."""
    window, card_view = make_window_with_card_view(qtbot)
    window.toggle_tab_fullscreen()
    assert not window.menuBar().isVisible()

    activate(qtbot, window, card_view.image_view)
    ctrl(qtbot, card_view.image_view, Qt.Key.Key_C)

    assert clipboard.mimeData().hasFormat(CARD_MIME)


def test_ctrl_c_in_a_note_copies_the_text_not_the_card(qtbot, clipboard):
    window, card_view = make_window_with_card_view(qtbot)
    notes = card_view.notes_tab
    card_view.info_tabs.setCurrentWidget(notes)
    notes.stack.setCurrentWidget(notes.editor_page)
    editor = notes.note_editor
    editor.setEnabled(True)
    editor.setPlainText("The Tower, again")
    editor.selectAll()

    activate(qtbot, window, editor)
    ctrl(qtbot, editor, Qt.Key.Key_C)

    assert clipboard.text() == "The Tower, again"
    assert not clipboard.mimeData().hasFormat(CARD_MIME)


def test_ctrl_c_in_esoterica_copies_the_text_not_the_card(qtbot, clipboard, monkeypatch):
    from types import SimpleNamespace

    from PyQt6.QtWidgets import QLabel

    from tarot_canvas.models.esoterica import Passage
    from tarot_canvas.ui.tabs.card_view import esoterica_tab

    passages = [Passage("A Source", None, "Selectable passage text.")]
    manager = SimpleNamespace(get_passages_for_card=lambda _card_id: passages)
    monkeypatch.setattr(esoterica_tab, "get_esoterica_manager", lambda: manager)

    window, card_view = make_window_with_card_view(qtbot)
    card_view.info_tabs.setCurrentWidget(card_view.esoterica_tab)
    text = card_view.esoterica_tab.passage_widgets[0].findChildren(QLabel)[-1]
    qtbot.waitUntil(text.isVisible)

    activate(qtbot, window, text)
    text.setSelection(0, len("Selectable"))
    assert text.selectedText() == "Selectable"
    ctrl(qtbot, text, Qt.Key.Key_C)

    assert clipboard.text() == "Selectable"
    assert not clipboard.mimeData().hasFormat(CARD_MIME)
