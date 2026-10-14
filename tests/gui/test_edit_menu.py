"""The Edit menu asks the focused text, then the current tab"""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLineEdit, QMenu

from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.card_transfer import CARD_MIME, card_from_mime
from tarot_canvas.ui.command_palette import CommandPalette
from tests.gui.test_main_window import activate, make_shown_window

CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
ALT = Qt.KeyboardModifier.AltModifier


def cards_on(canvas):
    return [item for item in canvas.scene.items() if isinstance(item, DraggableCardItem)]


def canvas_with_cards(qtbot, deck, count=2, reversed_=False):
    window = make_shown_window(qtbot)
    canvas = window.new_canvas_tab()
    for card in deck.get_all_cards()[:count]:
        canvas.add_specific_card(card, card_deck=deck, is_reversed=reversed_)
    activate(qtbot, window, canvas.view)
    return window, canvas


@pytest.fixture
def no_timers(qtbot):
    yield
    # The canvas's timers must not outlive it
    qtbot.wait(1100)


def test_ctrl_a_selects_every_card_and_ctrl_shift_a_clears(qtbot, minimal_deck, no_timers):
    window, canvas = canvas_with_cards(qtbot, minimal_deck)
    canvas.scene.clearSelection()

    qtbot.keyClick(canvas.view, Qt.Key.Key_A, CTRL)
    assert len(canvas.scene.selectedItems()) == 2

    qtbot.keyClick(canvas.view, Qt.Key.Key_A, CTRL | SHIFT)
    assert canvas.scene.selectedItems() == []
    assert not window.edit_actions["deselect"].isEnabled()


def test_a_copied_canvas_card_keeps_its_deck_and_orientation(
    qtbot, clipboard, other_deck, no_timers
):
    window, canvas = canvas_with_cards(qtbot, other_deck, count=1, reversed_=True)
    (item,) = cards_on(canvas)
    assert window.copy_card_action.isEnabled()

    qtbot.keyClick(canvas.view, Qt.Key.Key_C, CTRL)

    card, deck, is_reversed = card_from_mime(clipboard.mimeData(), [other_deck])
    assert card["id"] == item.card_data["id"]
    assert deck is other_deck
    assert is_reversed

    second = window.new_canvas_tab()
    window.paste_card_action.trigger()
    (pasted,) = cards_on(second)
    assert pasted.deck is other_deck
    assert pasted.is_reversed()


def test_ctrl_x_moves_the_card_onto_the_clipboard(qtbot, clipboard, minimal_deck, no_timers):
    window, canvas = canvas_with_cards(qtbot, minimal_deck, count=1)

    qtbot.keyClick(canvas.view, Qt.Key.Key_X, CTRL)

    assert cards_on(canvas) == []
    assert clipboard.mimeData().hasFormat(CARD_MIME)


def test_copy_and_cut_take_one_card_and_not_two(qtbot, minimal_deck, no_timers):
    window, canvas = canvas_with_cards(qtbot, minimal_deck)
    for item in cards_on(canvas):
        item.setSelected(True)

    assert not window.copy_card_action.isEnabled()
    assert not window.edit_actions["cut"].isEnabled()
    assert window.edit_actions["delete"].isEnabled()


@pytest.mark.parametrize("key", [Qt.Key.Key_Delete, Qt.Key.Key_Backspace])
def test_del_and_backspace_remove_the_selected_cards(qtbot, minimal_deck, key, no_timers):
    window, canvas = canvas_with_cards(qtbot, minimal_deck)
    first, second = cards_on(canvas)
    canvas.scene.clearSelection()
    first.setSelected(True)

    qtbot.keyClick(canvas.view, key)

    assert cards_on(canvas) == [second]


def test_align_and_fit_have_their_new_keys(qtbot, minimal_deck, monkeypatch, no_timers):
    window, canvas = canvas_with_cards(qtbot, minimal_deck)
    shown = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, *args: shown.append(menu))
    fitted = []
    monkeypatch.setattr(canvas.view, "fit_to_rect", fitted.append)
    for item in cards_on(canvas):
        item.setSelected(True)

    qtbot.keyClick(canvas.view, Qt.Key.Key_A, CTRL | ALT)
    qtbot.keyClick(canvas.view, Qt.Key.Key_F, SHIFT)

    assert len(shown) == 1
    assert len(fitted) == 1
    assert len(canvas.scene.selectedItems()) == 2, "Ctrl+Alt+A is not Select All"


def test_the_edit_keys_work_with_the_menu_bar_hidden(qtbot, minimal_deck, no_timers):
    window, canvas = canvas_with_cards(qtbot, minimal_deck)
    window.toggle_tab_fullscreen()
    assert not window.menuBar().isVisible()
    activate(qtbot, window, canvas.view)
    canvas.scene.clearSelection()

    qtbot.keyClick(canvas.view, Qt.Key.Key_A, CTRL)
    qtbot.keyClick(canvas.view, Qt.Key.Key_Delete)

    assert cards_on(canvas) == []


def test_edit_copy_takes_a_focused_fields_selected_text(qtbot, clipboard):
    window = make_shown_window(qtbot)
    window.new_card_view_tab()
    card_view = window.tab_widget.currentWidget()
    field = QLineEdit("Death is change", card_view)
    field.show()
    activate(qtbot, window, field)

    field.setSelection(0, 5)
    window.copy_card_action.trigger()
    assert clipboard.text() == "Death"
    assert not clipboard.mimeData().hasFormat(CARD_MIME)

    # With nothing selected the card is copied, as it would be from anywhere else
    field.deselect()
    window.copy_card_action.trigger()
    assert clipboard.mimeData().hasFormat(CARD_MIME)


def test_edit_select_all_and_delete_act_on_a_focused_field(qtbot):
    window = make_shown_window(qtbot)
    library = window.new_library_tab()
    activate(qtbot, window, library.search_field)
    library.search_field.setText("moon")

    window.update_edit_actions()
    assert window.edit_actions["select_all"].isEnabled()
    window.edit_actions["select_all"].trigger()
    window.edit_actions["delete"].trigger()

    assert library.search_field.text() == ""


def test_ctrl_f_in_a_library_goes_to_its_search_field(qtbot):
    window = make_shown_window(qtbot)
    library = window.new_library_tab()
    activate(qtbot, window, library.sidebar)

    qtbot.keyClick(library.sidebar, Qt.Key.Key_F, CTRL)

    assert QApplication.focusWidget() is library.search_field


def test_ctrl_f_on_a_canvas_opens_find_card(qtbot, minimal_deck, monkeypatch, no_timers):
    opened = []
    monkeypatch.setattr(CommandPalette, "exec", lambda palette: opened.append(palette))
    window, canvas = canvas_with_cards(qtbot, minimal_deck, count=0)

    qtbot.keyClick(canvas.view, Qt.Key.Key_F, CTRL)

    assert len(opened) == 1
