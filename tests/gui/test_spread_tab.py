import math

import pytest
from PyQt6.QtCore import QModelIndex, QPoint, QPointF, QRect, QSize, Qt
from PyQt6.QtGui import QKeySequence, QMouseEvent, QWheelEvent
from PyQt6.QtWidgets import QApplication, QMessageBox, QStyleOptionViewItem, QToolButton

from tarot_canvas.models import spreads
from tarot_canvas.models.spreads import Position, Spread
from tarot_canvas.settings import CANVAS_GUIDES_KEY, get_settings
from tarot_canvas.ui import commands
from tarot_canvas.ui.canvas.slot_item import SlotItem
from tarot_canvas.ui.canvas.spread_pane import MeaningRole, NumberRole
from tarot_canvas.ui.canvas.view import MIN_ZOOM
from tarot_canvas.ui.card_transfer import card_mime_data, copy_card_to_clipboard
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import COMMANDS, SPREADS
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.spread_tab import SpreadTab
from tarot_canvas.ui.widgets.reorder_list import GRIP_WIDTH

Answer = QMessageBox.StandardButton
UNIT = 200


@pytest.fixture(autouse=True)
def card_unit(monkeypatch):
    """The stub deck's art is one pixel square"""
    size = QSize(UNIT, 340)
    monkeypatch.setattr("tarot_canvas.ui.canvas.slot_item.card_unit_size", lambda: size)
    monkeypatch.setattr("tarot_canvas.ui.tabs.spread_tab.card_unit_size", lambda: size)


def make_tab(qtbot, *args):
    tab = SpreadTab(*args)
    qtbot.addWidget(tab)
    tab.resize(1000, 700)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


def add_slots(tab, count):
    return [tab.add_next_slot(QPointF(index * 300, 0)) for index in range(count)]


def image(slot):
    return slot.pixmap().toImage()


def select(tab, slot):
    tab.scene.clearSelection()
    slot.setSelected(True)


def row_rect(tab, row):
    view = tab.pane.list_view
    return view.visualRect(tab.positions.index(row))


def listed(tab):
    """Each row's number and label, in row order"""
    return [
        (tab.positions.index(row).data(NumberRole), tab.positions.index(row).data())
        for row in range(tab.positions.rowCount())
    ]


def click_row(qtbot, tab, row):
    view = tab.pane.list_view
    qtbot.mouseClick(
        view.viewport(), Qt.MouseButton.LeftButton, pos=row_rect(tab, row).topLeft() + QPoint(4, 4)
    )


def centre(slot):
    return slot.pos() + slot.boundingRect().center()


@pytest.fixture(autouse=True)
def discard_on_teardown(monkeypatch):
    """A window left with unsaved work would otherwise wait on a dialog as it closes"""
    monkeypatch.setattr(
        "tarot_canvas.ui.main_window.QMessageBox.warning", lambda *_: Answer.Discard
    )


@pytest.fixture
def window(qtbot, spreads_base):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


# -- slots


def test_each_added_slot_takes_the_next_number_and_id(qtbot):
    tab = make_tab(qtbot)
    slots = [tab.commands["canvas.summon"].trigger() or tab.slots()[-1] for _ in range(3)]

    assert [slot.number for slot in slots] == [1, 2, 3]
    assert [slot.position_id for slot in slots] == ["p1", "p2", "p3"]


def test_the_summon_command_adds_a_slot_here_and_has_no_flip(qtbot):
    tab = make_tab(qtbot)
    ids = [action.objectName() for action in tab.toolbar.actions()]
    add_slot = tab.commands["canvas.summon"]

    assert "canvas.summon" in ids
    assert "canvas.rotate" in ids
    assert "canvas.flip" not in tab.commands
    assert add_slot.text() == COMMANDS["add_slot"]
    assert add_slot.toolTip() == f'{SPREADS["add_slot_tooltip"]} (D)'


def test_a_slot_takes_the_key_a_summon_is_given(qtbot):
    tab = make_tab(qtbot)

    commands.store_keys("canvas.summon", ["G"])
    commands.apply_shortcuts()

    assert tab.commands["canvas.summon"].shortcut() == QKeySequence("G")
    assert tab.commands["canvas.summon"].toolTip() == f'{SPREADS["add_slot_tooltip"]} (G)'


def test_a_plain_canvas_still_summons(qtbot):
    tab = CanvasTab()
    qtbot.addWidget(tab)

    assert tab.commands["canvas.summon"].text() == COMMANDS["summon_card"]


def test_double_clicking_the_canvas_adds_a_slot_there(qtbot):
    tab = make_tab(qtbot)
    tab.view.background_double_clicked.emit(QPointF(40, 60))

    (slot,) = tab.cards()
    assert isinstance(slot, SlotItem)
    assert centre(slot) == QPointF(40, 60)


def test_deleting_a_slot_renumbers_those_after_it_and_keeps_their_ids(qtbot):
    tab = make_tab(qtbot)
    first, second, third = add_slots(tab, 3)
    before = image(third)

    select(tab, second)
    tab.commands["canvas.delete"].trigger()

    assert tab.slots() == (first, third)
    assert [slot.number for slot in tab.slots()] == [1, 2]
    assert [slot.position_id for slot in tab.slots()] == ["p1", "p3"]
    assert image(third) != before


def test_a_new_slot_after_a_delete_takes_a_fresh_id(qtbot):
    tab = make_tab(qtbot)
    first, second, third = add_slots(tab, 3)
    select(tab, second)
    tab.on_delete_card()

    assert tab.add_next_slot().position_id == "p4"


def test_a_slot_menu_has_only_rotate_and_delete(qtbot):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)

    menu = tab.card_menu(centre(slot))

    assert [action.isSeparator() or action.text() for action in menu.actions()] == [
        tab.commands["canvas.rotate"].text(),
        True,
        tab.commands["canvas.delete"].text(),
    ]


def test_a_pasted_card_becomes_a_slot(qtbot, clipboard, minimal_deck):
    tab = make_tab(qtbot)
    card = minimal_deck.get_random_card()
    copy_card_to_clipboard(card, minimal_deck, False)

    tab.on_paste_card()

    (slot,) = tab.cards()
    assert isinstance(slot, SlotItem)
    assert (slot.label, slot.meaning) == ("", "")
    assert tab.slots() == (slot,)


def test_a_dropped_card_becomes_a_slot_where_it_landed(qtbot, minimal_deck):
    tab = make_tab(qtbot)
    card = minimal_deck.get_random_card()

    tab.on_card_dropped(card_mime_data(card, minimal_deck, False), QPointF(70, 90))

    (slot,) = tab.cards()
    assert isinstance(slot, SlotItem)
    assert centre(slot) == QPointF(70, 90)


# -- the pane


def test_every_slot_is_a_row_in_number_order(qtbot):
    tab = make_tab(qtbot)
    first, second, third = add_slots(tab, 3)
    second.set_label("Past")
    tab.positions.setData(tab.positions.index(1), "Past")

    tab.pane.list_view.move_row(2, 0)

    assert listed(tab) == [(1, ""), (2, ""), (3, "Past")]


def test_a_label_with_no_meaning_is_level_with_its_number(qtbot):
    tab = make_tab(qtbot)
    delegate = tab.pane.delegate
    option = QStyleOptionViewItem()
    option.font = tab.pane.list_view.font()
    option.rect = QRect(0, 0, 300, delegate.sizeHint(option, QModelIndex()).height())
    number = delegate._number_rect(option)

    alone = delegate.title_rect(option, has_meaning=False)
    over_a_meaning = delegate.title_rect(option, has_meaning=True)

    assert abs(alone.center().y() - number.center().y()) <= 1
    assert over_a_meaning.top() == number.top()


def test_a_row_reads_as_its_number_and_label(qtbot):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)
    slot.set_label("Past")

    text = tab.positions.index(0).data(Qt.ItemDataRole.AccessibleTextRole)

    assert text == SPREADS["slot_row"].format(number=1, label="Past")


def test_one_selected_slot_opens_its_row(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    select(tab, first)
    first.set_label("Past")
    first.meaning = "Before"

    select(tab, second)
    assert tab.pane.editor.label_edit.text() == ""
    select(tab, first)

    view = tab.pane.list_view
    assert view.indexWidget(tab.positions.index(0)) is tab.pane.editor
    assert view.indexWidget(tab.positions.index(1)) is None
    assert tab.pane.editor.label_edit.text() == "Past"
    assert tab.pane.editor.meaning_edit.toPlainText() == "Before"
    assert row_rect(tab, 0).height() > row_rect(tab, 1).height()


def test_the_open_row_leaves_the_grip_exposed(qtbot):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)
    qtbot.wait(0)

    left = tab.pane.editor.geometry().left()

    assert left >= GRIP_WIDTH
    assert tab.pane.list_view.indexAt(QPoint(4, row_rect(tab, 0).center().y())).row() == 0


def test_nothing_or_several_selected_opens_no_row(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    view = tab.pane.list_view

    tab.scene.clearSelection()
    assert tab.pane.editor is None
    assert view.indexWidget(tab.positions.index(1)) is None
    assert not view.selectionModel().hasSelection()

    first.setSelected(True)
    assert tab.pane.editor is not None

    second.setSelected(True)
    assert tab.pane.editor is None
    assert view.indexWidget(tab.positions.index(0)) is None


def test_selecting_on_the_canvas_selects_the_row(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)

    select(tab, first)

    assert [index.row() for index in tab.pane.list_view.selectedIndexes()] == [0]


def test_clicking_a_row_selects_its_slot_alone(qtbot):
    tab = make_tab(qtbot)
    first, second, third = add_slots(tab, 3)
    first.setSelected(True)
    second.setSelected(True)

    click_row(qtbot, tab, 2)

    assert tab.selected_cards() == [third]
    assert tab.pane.list_view.indexWidget(tab.positions.index(2)) is tab.pane.editor


def test_typing_a_label_changes_the_slot_and_its_face_and_keeps_focus(qtbot):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)
    before = image(slot)
    editor = tab.pane.editor
    qtbot.keyClicks(editor.label_edit, "Past")

    assert slot.label == "Past"
    assert image(slot) != before
    assert tab.pane.editor is editor
    assert tab.positions.index(0).data() == "Past"


def test_typing_a_meaning_changes_the_slot(qtbot):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)

    qtbot.keyClicks(tab.pane.editor.meaning_edit, "Before")

    assert slot.meaning == "Before"
    assert tab.positions.index(0).data(MeaningRole) == "Before"


def test_reselecting_the_slot_keeps_the_editor(qtbot):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)
    editor = tab.pane.editor

    tab.scene.selectionChanged.emit()

    assert tab.pane.editor is editor


def test_a_drop_renumbers_keeps_ids_and_modifies_the_spread(qtbot, spreads_base):
    tab = make_tab(qtbot)
    first, second, third = add_slots(tab, 3)
    tab.save()
    select(tab, first)
    view = tab.pane.list_view
    changes = []
    tab.layout_changed.connect(lambda: changes.append(1))

    view.move_row(0, view.drop_row(row_rect(tab, 2).bottomLeft()))

    assert tab.slots() == (second, third, first)
    assert [slot.number for slot in tab.slots()] == [1, 2, 3]
    assert [slot.position_id for slot in tab.slots()] == ["p2", "p3", "p1"]
    assert len(changes) == 1
    assert tab.has_unsaved_changes()


def test_a_moved_slot_keeps_its_open_row(qtbot):
    tab = make_tab(qtbot)
    first, second, third = add_slots(tab, 3)
    select(tab, first)
    editor = tab.pane.editor

    tab.pane.list_view.move_row(0, 3)

    assert tab.pane.editor is editor
    assert tab.pane.list_view.indexWidget(tab.positions.index(2)) is editor


def test_the_row_buttons_move_the_slot_and_stop_at_the_ends(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    select(tab, first)
    editor = tab.pane.editor
    assert not editor.earlier_button.isEnabled()

    editor.later_button.click()

    assert tab.slots() == (second, first)
    assert editor.earlier_button.isEnabled()
    assert not editor.later_button.isEnabled()

    editor.earlier_button.click()

    assert tab.slots() == (first, second)


def test_a_row_far_down_the_list_scrolls_into_view_when_it_opens(qtbot):
    tab = make_tab(qtbot)
    slots = add_slots(tab, 30)
    tab.scene.clearSelection()

    select(tab, slots[-1])
    qtbot.wait(0)

    assert tab.pane.list_view.viewport().rect().contains(row_rect(tab, 29))


def test_alt_arrows_in_the_label_field_move_the_slot(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    select(tab, first)

    qtbot.keyClick(tab.pane.editor.label_edit, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)

    assert tab.slots() == (second, first)


def test_deleting_the_open_slot_opens_no_other(qtbot):
    tab = make_tab(qtbot)
    first, second, third = add_slots(tab, 3)
    select(tab, second)

    tab.on_delete_card()

    assert tab.pane.editor is None
    assert tab.selected_cards() == []
    assert tab.positions.rowCount() == 2
    assert listed(tab) == [(1, ""), (2, "")]


def test_a_new_slot_opens_its_row(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    select(tab, first)
    tab.on_delete_card()

    third = tab.add_next_slot()

    assert tab.selected_cards() == [third]
    assert tab.pane.list_view.indexWidget(tab.positions.index(1)) is tab.pane.editor


def test_deleting_an_earlier_slot_keeps_the_later_row_right(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    second.set_label("Next")
    select(tab, first)
    tab.on_delete_card()
    select(tab, second)

    assert tab.pane.editor.label_edit.text() == "Next"
    assert tab.pane.list_view.indexWidget(tab.positions.index(0)) is tab.pane.editor


def test_an_empty_spread_shows_the_placeholder_and_it_adds_a_slot(qtbot):
    tab = make_tab(qtbot)
    assert tab.pane.stack.currentIndex() == 1
    assert tab.pane.placeholder.heading.text() == SPREADS["slots_empty"]

    tab.pane.placeholder.helpful_button.click()

    assert len(tab.slots()) == 1
    assert tab.pane.stack.currentWidget() is tab.pane.list_view


def test_deleting_the_last_slot_brings_the_placeholder_back(qtbot):
    tab = make_tab(qtbot)
    add_slots(tab, 1)

    tab.on_delete_card()

    assert tab.pane.stack.currentIndex() == 1


def test_a_stored_spread_opens_with_no_row_open(window, spreads_base):
    tab = window.open_spread(stored(spreads_base))

    assert tab.pane.editor is None
    assert listed(tab) == [(1, "Past"), (2, "Next")]


def test_the_toolbar_toggle_collapses_the_pane(qtbot):
    tab = make_tab(qtbot)
    assert tab.pane.is_open()

    tab.pane_action.trigger()
    assert not tab.pane.is_open()

    tab.pane_action.trigger()
    assert tab.pane.is_open()


# -- the description


def test_a_new_spread_starts_with_the_description_open_and_its_button_closes_it(qtbot):
    tab = make_tab(qtbot)
    assert tab.pane.description_edit.isVisible()

    tab.pane.description_button.click()
    assert not tab.pane.description_edit.isVisible()

    tab.pane.description_button.click()
    assert tab.pane.description_edit.isVisible()


def test_a_stored_description_opens_the_section(window, spreads_base):
    tab = window.open_spread(stored(spreads_base))

    assert tab.pane.description_open()


def test_a_stored_spread_with_no_description_starts_with_it_closed(window, spreads_base):
    path = spreads_base / "1000"
    path.mkdir(parents=True)
    spreads.save(path, Spread(name="Plain"))

    assert not window.open_spread(path).pane.description_open()


def test_each_tab_has_its_own_section_state(qtbot):
    first, second = make_tab(qtbot), make_tab(qtbot)

    first.pane.description_button.click()

    assert not first.pane.description_open()
    assert second.pane.description_open()


LONG_TEXT = "\n\n".join(f"Paragraph {number}" for number in range(20))


def test_an_empty_description_is_one_line_high_with_no_expand_button(qtbot):
    tab = make_tab(qtbot)
    pane = tab.pane

    assert pane.description_edit.height() < 2 * pane.fontMetrics().lineSpacing() + 12
    assert not pane.expand_button.isVisible()


def test_the_description_grows_with_its_text_up_to_its_limit(qtbot):
    tab = make_tab(qtbot)
    box = tab.pane.description_edit
    empty = box.height()

    box.setPlainText("One\nTwo\nThree")
    assert box.height() > empty
    assert not tab.pane.expand_button.isVisible()

    three_lines = box.height()
    box.setPlainText(LONG_TEXT)
    assert box.height() > three_lines
    limit = box.height()

    box.setPlainText(LONG_TEXT + LONG_TEXT)
    assert box.height() == limit


def test_wrapped_lines_count_towards_the_limit(qtbot):
    tab = make_tab(qtbot)

    tab.pane.description_edit.setPlainText("word " * 500)

    assert tab.pane.expand_button.isVisible()


def test_four_lines_fit_and_a_fifth_offers_the_button(qtbot):
    tab = make_tab(qtbot)
    box = tab.pane.description_edit

    box.setPlainText("1\n2\n3\n4")
    assert not box.overflowing

    box.setPlainText("1\n2\n3\n4\n5")
    assert box.overflowing
    assert tab.pane.expand_button.isVisible()


def test_expanding_trades_the_list_for_the_description_and_back(qtbot):
    tab = make_tab(qtbot)
    add_slots(tab, 2)
    pane = tab.pane
    pane.description_edit.setPlainText(LONG_TEXT)
    compact = pane.description_edit.height()

    pane.expand_button.click()
    qtbot.waitUntil(lambda: pane.description_edit.height() > compact)
    assert not pane.stack.isVisible()
    assert pane.name_edit.isVisible()

    pane.expand_button.click()
    assert pane.stack.isVisible()
    assert pane.description_edit.height() == compact


def test_expanded_text_cut_short_can_still_be_collapsed(qtbot):
    tab = make_tab(qtbot)
    pane = tab.pane
    pane.description_edit.setPlainText(LONG_TEXT)
    pane.expand_button.click()

    pane.description_edit.setPlainText("Short")
    assert pane.expand_button.isVisible()

    pane.expand_button.click()
    assert not pane.expand_button.isVisible()
    assert pane.stack.isVisible()


def test_selecting_a_slot_brings_the_list_back(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    pane = tab.pane
    pane.description_edit.setPlainText(LONG_TEXT)
    pane.expand_button.click()

    select(tab, first)

    assert pane.stack.isVisible()
    assert not pane.description_expanded()


def test_folding_an_expanded_description_brings_the_list_back(qtbot):
    tab = make_tab(qtbot)
    pane = tab.pane
    pane.description_edit.setPlainText(LONG_TEXT)
    pane.expand_button.click()

    pane.description_button.click()

    assert pane.stack.isVisible()
    assert not pane.expand_button.isVisible()


def test_a_stored_long_description_offers_the_button(qtbot, window, spreads_base):
    path = spreads_base / "1000"
    path.mkdir(parents=True)
    spreads.save(path, Spread(name="Long", description=LONG_TEXT))
    window.show()
    qtbot.waitExposed(window)

    pane = window.open_spread(path).pane

    qtbot.waitUntil(pane.expand_button.isVisible)


def test_pasted_rich_text_stays_plain(qtbot):
    assert not make_tab(qtbot).pane.description_edit.acceptRichText()


def test_the_tab_has_no_band_over_the_canvas(qtbot):
    tab = make_tab(qtbot)

    assert tab.layout.count() == 1
    assert tab.layout.itemAt(0).widget() is tab.splitter


# -- the label


def test_the_tab_label_follows_the_name(qtbot):
    tab = make_tab(qtbot)
    assert tab.tab_title() == SPREADS["untitled"]

    with qtbot.waitSignal(tab.tab_label_changed):
        tab.rename("The Horseshoe")

    assert tab.display_name() == "The Horseshoe"


def test_the_name_field_starts_empty_and_says_what_it_is_for(qtbot):
    tab = make_tab(qtbot)

    assert tab.pane.name_edit.text() == ""
    assert tab.pane.name_edit.placeholderText() == SPREADS["name_hint"]
    assert tab.pane.name_edit.accessibleName() == SPREADS["name_title"]


def test_typing_in_the_name_field_names_the_tab_as_it_goes(window, qtbot):
    tab = window.new_spread_tab()
    index = window.tab_widget.indexOf(tab)

    qtbot.keyClicks(tab.pane.name_edit, "Sh")

    assert window.tab_widget.tabText(index) == SPREADS["unsaved_tab"].format(title="Sh")
    assert tab.slots() == ()


def test_clearing_the_name_field_goes_back_to_untitled(qtbot):
    tab = make_tab(qtbot)
    tab.pane.name_edit.setText("Named")

    tab.pane.name_edit.clear()

    assert tab.rename_text() == ""
    assert tab.display_name() == SPREADS["untitled"]


def test_a_stored_name_is_in_the_field(window, spreads_base):
    tab = window.open_spread(stored(spreads_base))

    assert tab.pane.name_edit.text() == "The Horseshoe"


def test_renaming_the_tab_sets_the_name(window, qtbot, monkeypatch):
    tab = window.new_spread_tab()
    index = window.tab_widget.indexOf(tab)
    tab.rename("Old")
    offered = []

    def answer(*_, text):
        offered.append(text)
        return "New", True

    monkeypatch.setattr("tarot_canvas.ui.main_window.QInputDialog.getText", answer)
    window.show_tab_rename_dialog(index)

    assert offered == ["Old"]
    assert tab.rename_text() == "New"
    assert tab.pane.name_edit.text() == "New"
    assert window.tab_widget.tabText(index) == SPREADS["unsaved_tab"].format(title="New")


# -- ways in


def test_new_spread_is_in_the_file_and_new_tab_menus_after_new_card_view(window):
    file_menu = window.menuBar().actions()[0].menu()
    actions = file_menu.actions()
    assert actions[actions.index(window.new_card_view_action) + 1] is window.new_spread_action

    new_tab_menu = next(
        button.menu()
        for button in window.findChildren(QToolButton)
        if button.menu() is not None and window.new_canvas_action in button.menu().actions()
    )
    actions = new_tab_menu.actions()
    assert actions[actions.index(window.new_card_view_action) + 1] is window.new_spread_action


def test_new_spread_opens_a_spread_tab(window):
    window.new_spread_action.trigger()

    tab = window.tab_widget.currentWidget()
    assert isinstance(tab, SpreadTab)
    assert window.tab_widget.tabText(window.tab_widget.currentIndex()) == SPREADS["untitled"]


# -- keeping it


def test_save_follows_open_deck_in_the_file_menu(window):
    actions = window.menuBar().actions()[0].menu().actions()
    open_deck = next(action for action in actions if action.text() == COMMANDS["open_deck"])

    assert actions[actions.index(open_deck) + 1] is window.save_action


def test_save_starts_disabled(window):
    assert not window.save_action.isEnabled()


def test_save_is_enabled_only_when_there_is_something_to_save(window, spreads_base):
    window.new_canvas_tab()
    assert not window.save_action.isEnabled()

    tab = window.new_spread_tab()
    assert window.save_action.isEnabled()

    window.save_action.trigger()
    assert tab.spread_path is not None
    assert not window.save_action.isEnabled()

    tab.rename("Changed")
    assert window.save_action.isEnabled()


def test_the_toolbar_has_no_save(qtbot):
    tab = make_tab(qtbot)

    assert "window.save" not in [action.objectName() for action in tab.toolbar.actions()]


def test_new_spread_has_a_key(window):
    assert window.new_spread_action.shortcut().toString() == "Ctrl+Shift+N"


def test_ctrl_s_writes_card_widths_about_the_layout_centre(qtbot, spreads_base):
    tab = make_tab(qtbot)
    tab.add_next_slot(QPointF(100, 50))
    second = tab.add_next_slot(QPointF(100 + 2 * UNIT, 50 + UNIT))
    tab.scene.clearSelection()
    second.setSelected(True)
    tab.on_rotate_card()

    tab.save()

    assert tab.spread_path.parent == spreads_base
    first, second = spreads.load(tab.spread_path).positions
    assert (first.x, first.y) == (-1.0, -0.5)
    assert (second.x, second.y) == (1.0, 0.5)
    assert (first.rotation, second.rotation) == (0.0, 90.0)
    assert first.z < second.z


def test_a_slot_turned_by_the_wheel_saves_and_reopens_at_its_angle(qtbot, spreads_base):
    tab = make_tab(qtbot)
    slot, _ = add_slots(tab, 2)
    viewport = tab.view.viewport()
    pos = tab.view.mapFromScene(slot.sceneBoundingRect().center())
    QApplication.sendEvent(
        viewport,
        QWheelEvent(
            QPointF(pos),
            QPointF(viewport.mapToGlobal(pos)),
            QPoint(),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        ),
    )

    tab.save()

    first, second = spreads.load(tab.spread_path).positions
    assert (first.rotation, second.rotation) == (15.0, 0.0)
    window = MainWindow()
    qtbot.addWidget(window)
    reopened, _ = window.open_spread(tab.spread_path).slots()
    assert reopened.orient == 15


def send_mouse(tab, kind, pos, button, buttons):
    viewport = tab.view.viewport()
    QApplication.sendEvent(
        viewport,
        QMouseEvent(
            kind,
            QPointF(pos),
            QPointF(viewport.mapToGlobal(pos)),
            button,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        ),
    )


def test_a_slot_dragged_near_a_centre_line_saves_level_with_it(qtbot, spreads_base):
    get_settings().setValue(CANVAS_GUIDES_KEY, True)
    tab = make_tab(qtbot)
    first, second, _ = add_slots(tab, 3)
    second.setPos(second.pos() + QPointF(0, 200))
    tab.save()
    changes = []
    tab.layout_changed.connect(lambda: changes.append(1))

    left = Qt.MouseButton.LeftButton
    start = tab.view.mapFromScene(centre(second))
    goal = tab.view.mapFromScene(centre(second) - QPointF(0, 200)) + QPoint(0, 3)
    send_mouse(tab, QMouseEvent.Type.MouseButtonPress, start, left, left)
    for step in range(1, 4):
        send_mouse(
            tab,
            QMouseEvent.Type.MouseMove,
            start + (goal - start) * step / 3,
            Qt.MouseButton.NoButton,
            left,
        )
    send_mouse(tab, QMouseEvent.Type.MouseButtonRelease, goal, left, Qt.MouseButton.NoButton)

    assert len(changes) == 1
    assert tab.has_unsaved_changes()
    tab.save()
    saved_first, saved_second, _ = spreads.load(tab.spread_path).positions
    assert saved_second.y == saved_first.y


def test_save_is_disabled_until_the_next_change(qtbot, spreads_base):
    tab = make_tab(qtbot)
    tab.save()
    folder = tab.spread_path
    assert not tab.can_save()

    tab.rename("Again")
    assert tab.can_save()

    tab.save()
    assert not tab.can_save()
    assert tab.spread_path == folder
    assert len(list(spreads_base.iterdir())) == 1


def test_nothing_is_written_before_the_first_save(qtbot, spreads_base):
    tab = make_tab(qtbot)
    add_slots(tab, 1)
    tab.rename("Nope")

    assert not spreads_base.exists()


def test_an_edit_reaches_the_file_only_when_saved(qtbot, spreads_base):
    tab = make_tab(qtbot)
    tab.save()

    tab.rename("The Horseshoe")
    qtbot.wait(50)
    assert spreads.load(tab.spread_path).name == ""

    tab.save()
    assert spreads.load(tab.spread_path).name == "The Horseshoe"


@pytest.mark.parametrize(
    "change",
    [
        lambda tab: tab.add_next_slot(),
        lambda tab: tab.on_rotate_card(),
        lambda tab: tab.on_turn_card_by_wheel(tab.slots()[0], 1, False),
        lambda tab: tab.on_delete_card(),
        lambda tab: tab.on_bring_to_front(),
        lambda tab: tab.on_send_to_back(),
        lambda tab: tab.pane.list_view.move_row(1, 0),
        lambda tab: tab.pane.description_edit.setPlainText("Use it"),
        lambda tab: tab.pane.editor.label_edit.setText("Past"),
        lambda tab: tab.pane.editor.meaning_edit.setPlainText("Before"),
        lambda tab: tab.rename("Named"),
    ],
)
def test_every_kind_of_change_modifies_the_spread(qtbot, spreads_base, change):
    tab = make_tab(qtbot)
    first, _ = add_slots(tab, 2)
    select(tab, first)
    tab.save()
    assert not tab.has_unsaved_changes()

    change(tab)

    assert tab.has_unsaved_changes()


def test_a_drag_modifies_the_spread_when_it_ends(qtbot, spreads_base):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)
    tab.save()

    slot.begin_drag()
    assert not tab.has_unsaved_changes()

    slot.end_drag()
    assert tab.has_unsaved_changes()


def test_a_press_with_no_drag_changes_nothing(qtbot, spreads_base):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)
    tab.save()

    slot.end_drag()

    assert not tab.has_unsaved_changes()


def test_selecting_a_slot_changes_nothing(qtbot, spreads_base):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    tab.save()

    select(tab, first)
    select(tab, second)
    tab.pane.list_view.setCurrentIndex(tab.positions.index(0))

    assert not tab.has_unsaved_changes()


def test_an_arrangement_from_the_align_menu_modifies_the_spread(qtbot, spreads_base, monkeypatch):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    first.setSelected(True)
    second.setSelected(True)
    tab.save()

    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.canvas_tab.QMenu.exec",
        lambda menu, *_: menu.triggered.emit(menu.actions()[0]),
    )
    tab.on_align_cards()

    assert tab.has_unsaved_changes()


def arc_over_the_top(tab, follow=False):
    """Arrange on Arc: a rainbow, the default bend of 180, applied"""
    popover = tab.open_arc_popover()
    popover.follow.setChecked(follow)
    popover.apply()


def test_slots_go_round_an_arc_in_number_order(qtbot):
    tab = make_tab(qtbot)
    slots = add_slots(tab, 5)
    for index, slot in enumerate(slots):
        slot.setZValue(10 - index)  # so z order is the reverse of number order
    tab.scene.clearSelection()
    for index in (3, 0, 4, 2, 1):
        slots[index].setSelected(True)

    arc_over_the_top(tab)

    centres = [slot.pos() + slot.boundingRect().center() for slot in slots]
    xs = [centre.x() for centre in centres]
    assert xs == sorted(xs), "1 to 5, left to right"
    assert min(centres, key=lambda centre: centre.y()) == centres[2], "over the top"


def test_a_following_arc_saves_and_reopens_its_turns(qtbot, spreads_base):
    tab = make_tab(qtbot)
    for slot in add_slots(tab, 5):
        slot.setSelected(True)

    arc_over_the_top(tab, follow=True)
    tab.save()

    # Folded into (-90, 90], stored in [0, 360)
    expected = [288.0, 324.0, 0.0, 36.0, 72.0]
    rotations = [position.rotation for position in spreads.load(tab.spread_path).positions]
    assert rotations == pytest.approx(expected)
    window = MainWindow()
    qtbot.addWidget(window)
    reopened = window.open_spread(tab.spread_path).slots()
    assert [slot.orient for slot in reopened] == pytest.approx(expected)


def test_cancelling_an_arc_leaves_a_saved_spread_unmodified(qtbot, spreads_base):
    tab = make_tab(qtbot)
    for slot in add_slots(tab, 3):
        slot.setSelected(True)
    tab.save()

    popover = tab.open_arc_popover()
    popover.follow.setChecked(True)
    popover.close()

    assert not tab.has_unsaved_changes()


def test_applying_an_arc_modifies_the_spread(qtbot, spreads_base):
    tab = make_tab(qtbot)
    for slot in add_slots(tab, 3):
        slot.setSelected(True)
    tab.save()

    tab.open_arc_popover().apply()

    assert tab.has_unsaved_changes()


def test_the_pane_and_the_file_are_locked_while_an_arc_is_open(qtbot, spreads_base):
    tab = make_tab(qtbot)
    for slot in add_slots(tab, 3):
        slot.setSelected(True)
    tab.save()
    tab.mark_modified()

    popover = tab.open_arc_popover()
    tab._sync_menu()
    assert not tab.pane.list_view.isEnabled()
    assert not tab.duplicate_action.isEnabled()
    assert not tab.revert_action.isEnabled()
    assert not tab.can_save(), "the cards stand where the preview put them"

    popover.cancel()
    tab._sync_menu()
    assert tab.pane.list_view.isEnabled()
    assert tab.duplicate_action.isEnabled()
    assert tab.revert_action.isEnabled()
    assert tab.can_save()


def test_a_failed_write_keeps_the_tab_unsaved_and_leaves_no_folder(
    qtbot, spreads_base, monkeypatch
):
    def fail(*_):
        raise OSError("disk full")

    monkeypatch.setattr(spreads, "save", fail)
    tab = make_tab(qtbot)

    tab.save()

    assert tab.spread_path is None
    assert tab.can_save()
    assert list(spreads_base.iterdir()) == []


def test_a_failed_later_save_keeps_the_changes_and_the_folder(qtbot, spreads_base, monkeypatch):
    def fail(*_):
        raise OSError("disk full")

    tab = make_tab(qtbot)
    tab.save()
    folder = tab.spread_path
    tab.rename("Unkept")
    monkeypatch.setattr(spreads, "save", fail)

    assert not tab.save()

    assert tab.has_unsaved_changes()
    assert tab.spread_path == folder
    assert folder.is_dir()


def test_a_stored_sources_list_survives_a_save(window, spreads_base):
    tab = window.open_spread(stored(spreads_base))

    tab.rename("Renamed")
    tab.save()

    assert spreads.load(tab.spread_path).sources == ({"author": "Someone"},)


def test_every_write_announces_itself(qtbot, spreads_base):
    from tarot_canvas.models.spread_events import spread_events

    tab = make_tab(qtbot)
    with qtbot.waitSignal(spread_events().spreads_changed, timeout=500):
        tab.save()
    tab.rename("Again")
    with qtbot.waitSignal(spread_events().spreads_changed, timeout=500):
        tab.save()


# -- unsaved changes


def starred(name):
    return SPREADS["unsaved_tab"].format(title=name)


@pytest.mark.parametrize(
    "change",
    [
        lambda tab: tab.add_next_slot(),
        lambda tab: tab.pane.name_edit.setText("Named"),
        lambda tab: tab.pane.description_edit.setPlainText("Use it"),
    ],
)
def test_a_change_stars_the_tab(window, change):
    tab = window.new_spread_tab()
    index = window.tab_widget.indexOf(tab)
    assert window.tab_widget.tabText(index) == SPREADS["untitled"]

    change(tab)

    assert window.tab_widget.tabText(index).endswith("*")


def test_saving_takes_the_star_off_until_the_next_change(window, spreads_base):
    tab = window.new_spread_tab()
    tab.add_next_slot()
    index = window.tab_widget.indexOf(tab)
    assert window.tab_widget.tabText(index) == starred(SPREADS["untitled"])

    tab.save()
    assert window.tab_widget.tabText(index) == SPREADS["untitled"]

    tab.add_next_slot()
    assert window.tab_widget.tabText(index) == starred(SPREADS["untitled"])
    assert tab.has_unsaved_changes()


def test_an_opened_spread_has_no_star_until_it_changes(window, spreads_base):
    tab = window.open_spread(stored(spreads_base))
    index = window.tab_widget.indexOf(tab)
    assert window.tab_widget.tabText(index) == "The Horseshoe"

    tab.add_next_slot()
    assert window.tab_widget.tabText(index) == starred("The Horseshoe")


def answer_with(monkeypatch, button):
    asked = []

    def warning(_parent, title, text, _buttons, _default):
        asked.append((title, text))
        return button

    monkeypatch.setattr("tarot_canvas.ui.main_window.QMessageBox.warning", warning)
    return asked


def unsaved_tab(window):
    tab = window.new_spread_tab()
    tab.rename("Mine")
    return tab


def test_closing_an_untouched_spread_asks_nothing(window, monkeypatch):
    asked = answer_with(monkeypatch, Answer.Cancel)
    tab = window.new_spread_tab()

    window.close_tab(window.tab_widget.indexOf(tab))

    assert asked == []
    assert window.tab_widget.indexOf(tab) == -1


def test_cancel_keeps_the_tab(window, monkeypatch):
    asked = answer_with(monkeypatch, Answer.Cancel)
    tab = unsaved_tab(window)

    window.close_tab(window.tab_widget.indexOf(tab))

    assert asked == [
        (SPREADS["close_unsaved_title"], SPREADS["close_unsaved_text"].format(name="Mine"))
    ]
    assert window.tab_widget.indexOf(tab) >= 0
    assert tab.has_unsaved_changes()


def test_discard_closes_it_and_writes_nothing(window, spreads_base, monkeypatch):
    answer_with(monkeypatch, Answer.Discard)
    tab = unsaved_tab(window)

    window.close_tab(window.tab_widget.indexOf(tab))

    assert window.tab_widget.indexOf(tab) == -1
    assert not spreads_base.exists() or list(spreads_base.iterdir()) == []


def test_save_writes_it_and_closes(window, spreads_base, monkeypatch):
    answer_with(monkeypatch, Answer.Save)
    tab = unsaved_tab(window)

    window.close_tab(window.tab_widget.indexOf(tab))

    assert window.tab_widget.indexOf(tab) == -1
    assert spreads.load(tab.spread_path).name == "Mine"


def test_a_failed_save_keeps_the_tab(window, spreads_base, monkeypatch):
    def fail(*_):
        raise OSError("disk full")

    answer_with(monkeypatch, Answer.Save)
    monkeypatch.setattr(spreads, "save", fail)
    tab = unsaved_tab(window)

    window.close_tab(window.tab_widget.indexOf(tab))

    assert window.tab_widget.indexOf(tab) >= 0


def test_closing_a_saved_spread_asks_nothing(window, spreads_base, monkeypatch):
    asked = answer_with(monkeypatch, Answer.Cancel)
    tab = unsaved_tab(window)
    tab.save()

    window.close_tab(window.tab_widget.indexOf(tab))

    assert asked == []


def test_closing_a_spread_changed_since_its_save_asks(window, spreads_base, monkeypatch):
    asked = answer_with(monkeypatch, Answer.Cancel)
    tab = unsaved_tab(window)
    tab.save()
    tab.add_next_slot()

    window.close_tab(window.tab_widget.indexOf(tab))

    assert len(asked) == 1
    assert window.tab_widget.indexOf(tab) >= 0


def test_discarding_a_changed_spread_leaves_the_file_alone(window, spreads_base, monkeypatch):
    answer_with(monkeypatch, Answer.Discard)
    tab = window.open_spread(stored(spreads_base))
    tab.rename("Unkept")

    window.close_tab(window.tab_widget.indexOf(tab))

    assert spreads.load(tab.spread_path).name == "The Horseshoe"


def test_cancel_stops_the_window_closing_and_raises_the_tab(window, monkeypatch):
    answer_with(monkeypatch, Answer.Cancel)
    tab = unsaved_tab(window)
    window.new_canvas_tab()
    window.show()

    assert not window.close()
    assert window.tab_widget.currentWidget() is tab
    answer_with(monkeypatch, Answer.Discard)


def test_quitting_asks_about_each_unsaved_spread_in_turn(window, monkeypatch):
    asked = answer_with(monkeypatch, Answer.Discard)
    unsaved_tab(window).rename("One")
    unsaved_tab(window).rename("Two")
    window.show()

    assert window.close()
    assert [text for _, text in asked] == [
        SPREADS["close_unsaved_text"].format(name="One"),
        SPREADS["close_unsaved_text"].format(name="Two"),
    ]


# -- opening it


def stored_spread():
    return Spread(
        name="The Horseshoe",
        description="Left to right",
        sources=({"author": "Someone"},),
        positions=(
            Position("p1", "Past", "Before", -1.0, 0.25, 90.0, 5.0, {"x_keep": 1}),
            Position("p4", "Next", "After", 1.0, -0.25, 0.0, 2.0),
        ),
        extra={"x_tradition": "Golden Dawn"},
    )


def stored(base, name="1000"):
    path = base / name
    path.mkdir(parents=True)
    spreads.save(path, stored_spread())
    return path


def test_a_stored_spread_opens_as_it_was(window, spreads_base):
    tab = window.open_spread(stored(spreads_base))

    first, second = tab.slots()
    assert (first.number, first.position_id, first.label, first.meaning) == (
        1,
        "p1",
        "Past",
        "Before",
    )
    assert (second.number, second.position_id) == (2, "p4")
    assert centre(first) == QPointF(-UNIT, UNIT / 4)
    assert centre(second) == QPointF(UNIT, -UNIT / 4)
    assert (first.orient, second.orient) == (90.0, 0.0)
    assert (first.zValue(), second.zValue()) == (5.0, 2.0)
    assert tab.rename_text() == "The Horseshoe"
    assert tab.pane.description() == "Left to right"
    assert tab.current_spread().sources == ({"author": "Someone"},)
    assert window.tab_widget.tabText(window.tab_widget.indexOf(tab)) == "The Horseshoe"


def test_a_reopened_slot_does_not_animate_in(window, spreads_base):
    tab = window.open_spread(stored(spreads_base))

    for slot in tab.slots():
        assert not slot.isSelected()
        assert slot.motion.orient_lag == 0.0
        assert slot.motion.at_rest()


def test_opening_writes_nothing_and_modifies_nothing(window, spreads_base, qtbot):
    path = stored(spreads_base)
    file = path / "spread.toml"
    before = file.stat().st_mtime_ns

    tab = window.open_spread(path)

    qtbot.wait(50)
    assert file.stat().st_mtime_ns == before
    assert not tab.has_unsaved_changes()
    assert not tab.can_save()


def test_opening_twice_raises_the_tab(window, spreads_base):
    path = stored(spreads_base)
    tab = window.open_spread(path)
    window.new_canvas_tab()
    count = window.tab_widget.count()

    assert window.open_spread(path) is tab
    assert window.tab_widget.count() == count
    assert window.tab_widget.currentWidget() is tab


@pytest.mark.parametrize(
    "text",
    [
        "name = [",
        '[[positions]]\nid = "p1"\nx = nan\n',
        f'[[positions]]\nid = "p1"\nx = {"9" * 400}\n',
        f"k = {'[' * 5000}{']' * 5000}\n",
    ],
    ids=["not toml", "nan", "too large", "too deep"],
)
def test_an_unreadable_spread_opens_nothing(window, spreads_base, text):
    path = spreads_base / "1000"
    path.mkdir(parents=True)
    (path / "spread.toml").write_text(text)
    count = window.tab_widget.count()

    assert window.open_spread(path) is None
    assert window.tab_widget.count() == count


def test_saving_a_reopened_spread_keeps_its_unknown_keys_and_order(window, spreads_base):
    tab = window.open_spread(stored(spreads_base))

    tab.rename("Renamed")
    tab.save()

    loaded = spreads.load(tab.spread_path)
    assert loaded.name == "Renamed"
    assert loaded.extra == {"x_tradition": "Golden Dawn"}
    assert [position.id for position in loaded.positions] == ["p1", "p4"]
    assert loaded.positions[0].extra == {"x_keep": 1}


def test_a_slot_added_to_a_reopened_spread_goes_on_top(window, spreads_base):
    tab = window.open_spread(stored(spreads_base))

    assert tab.add_next_slot().zValue() > 5.0


def test_a_spread_saved_and_reopened_comes_back_in_place(window, spreads_base):
    tab = window.new_spread_tab()
    tab.add_next_slot(QPointF(0, 0)).set_label("One")
    tab.add_next_slot(QPointF(3 * UNIT, UNIT))
    select(tab, tab.slots()[1])
    tab.on_rotate_card()
    tab.save()
    path = tab.spread_path
    window.close_tab(window.tab_widget.indexOf(tab))

    reopened = window.open_spread(path)

    assert reopened is not tab
    first, second = reopened.slots()
    assert centre(second) - centre(first) == QPointF(3 * UNIT, UNIT)
    assert (first.label, second.orient) == ("One", 90.0)


def test_the_pane_starts_beside_the_canvas(qtbot):
    tab = make_tab(qtbot)
    assert tab.splitter.orientation() == Qt.Orientation.Horizontal
    assert tab.splitter.widget(0) is tab.canvas_area
    assert tab.splitter.widget(1) is tab.pane


# -- the pane's menu


def saved_tab(window, *slots):
    """A spread saved with a slot per label, unmodified"""
    tab = window.new_spread_tab()
    tab.pane.name_edit.setText("Mine")
    tab.pane.description_edit.setPlainText("Use it")
    for index, label in enumerate(slots):
        tab.add_next_slot(QPointF(index * 300, 0)).set_label(label)
    assert tab.save()
    return tab


def answer_warning(monkeypatch, answer):
    asked = []

    def warning(_parent, title, text, *_):
        asked.append((title, text))
        return answer

    monkeypatch.setattr(QMessageBox, "warning", warning)
    return asked


def enabled(tab):
    tab.pane.menu.aboutToShow.emit()
    return tab.revert_action.isEnabled(), tab.open_folder_action.isEnabled()


def test_the_menu_sits_beside_the_name_and_opens_at_once(qtbot):
    tab = make_tab(qtbot)
    button = tab.pane.menu_button

    assert button.menu() is tab.pane.menu
    assert button.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup
    assert button.geometry().left() >= tab.pane.name_edit.geometry().right()
    assert abs(button.geometry().center().y() - tab.pane.name_edit.geometry().center().y()) <= 1


def test_the_menu_lists_its_entries(qtbot):
    tab = make_tab(qtbot)
    entries = [action.text() for action in tab.pane.menu.actions() if not action.isSeparator()]

    assert entries == [SPREADS["duplicate"], SPREADS["revert"], SPREADS["open_folder"]]


def test_a_spread_with_no_folder_can_be_neither_reverted_nor_shown(window):
    tab = window.new_spread_tab()
    tab.add_next_slot()

    assert enabled(tab) == (False, False)


def test_revert_is_offered_only_with_changes_since_the_save(window):
    tab = saved_tab(window, "Past")
    assert enabled(tab) == (False, True)

    tab.pane.name_edit.setText("Other")
    assert enabled(tab) == (True, True)


def test_a_duplicate_is_a_new_unsaved_tab_of_the_current_state(window):
    tab = saved_tab(window, "Past", "Future")
    tab.slots()[1].set_orient(90)
    tab.pane.description_edit.setPlainText("Changed")

    tab.duplicate_action.trigger()

    copy = window.tab_widget.currentWidget()
    assert isinstance(copy, SpreadTab)
    assert copy is not tab
    assert copy.spread_path is None
    assert copy.has_unsaved_changes()
    assert window.tab_widget.tabText(window.tab_widget.indexOf(copy)) == starred("Mine")
    assert copy.current_spread() == tab.current_spread()


def test_saving_a_duplicate_leaves_the_original_folder_alone(window, spreads_base):
    tab = saved_tab(window, "Past")
    tab.duplicate_action.trigger()
    copy = window.tab_widget.currentWidget()

    copy.pane.name_edit.setText("Copy")
    assert copy.save()

    assert copy.spread_path != tab.spread_path
    assert spreads.load(tab.spread_path).name == "Mine"
    assert spreads.load(copy.spread_path).name == "Copy"


def test_a_duplicate_keeps_what_only_the_file_holds(window, spreads_base):
    path = spreads_base / "1"
    path.mkdir(parents=True)
    source = {"url": "https://example.com"}
    position = Position("p1", extra={"future": 1})
    spreads.save(path, Spread("Mine", sources=(source,), positions=(position,), extra={"k": 2}))
    tab = window.open_spread(path)

    tab.duplicate_action.trigger()

    copied = window.tab_widget.currentWidget().current_spread()
    assert copied.sources == (source,)
    assert copied.extra == {"k": 2}
    assert copied.positions[0].extra == {"future": 1}


def test_revert_restores_the_saved_spread(window, monkeypatch):
    tab = saved_tab(window, "Past", "Future")
    saved = tab.current_spread()
    answer_warning(monkeypatch, Answer.Discard)

    tab.pane.name_edit.setText("Other")
    tab.pane.description_edit.setPlainText("Changed")
    select(tab, tab.slots()[0])
    tab.commands["canvas.delete"].trigger()
    tab.add_next_slot(QPointF(900, 900)).set_label("New")

    tab.revert_action.trigger()

    assert tab.current_spread() == saved
    assert tab.pane.name_edit.text() == "Mine"
    assert listed(tab) == [(1, "Past"), (2, "Future")]
    assert len(tab.cards()) == 2
    assert tab.pane.editor is None
    assert not tab.has_unsaved_changes()
    assert window.tab_widget.tabText(window.tab_widget.indexOf(tab)) == "Mine"


def test_revert_asks_first_and_cancelling_keeps_the_changes(window, monkeypatch):
    tab = saved_tab(window, "Past")
    asked = answer_warning(monkeypatch, Answer.Cancel)
    tab.pane.name_edit.setText("Other")

    tab.revert_action.trigger()

    assert asked == [(SPREADS["revert_title"], SPREADS["revert_text"].format(name="Other"))]
    assert tab.pane.name_edit.text() == "Other"
    assert tab.has_unsaved_changes()


def test_a_folder_gone_from_disk_keeps_the_changes_on_revert(window, monkeypatch):
    tab = saved_tab(window, "Past")
    answer_warning(monkeypatch, Answer.Discard)
    tab.pane.name_edit.setText("Other")
    (tab.spread_path / spreads.SPREAD_FILE).unlink()

    tab.revert_action.trigger()

    assert listed(tab) == [(1, "Past")]
    assert tab.pane.name_edit.text() == "Other"
    assert tab.has_unsaved_changes()


def test_a_slot_added_after_a_revert_takes_the_next_number(window, monkeypatch):
    tab = saved_tab(window, "Past", "Future")
    answer_warning(monkeypatch, Answer.Discard)
    tab.add_next_slot()

    tab.revert_action.trigger()

    slot = tab.add_next_slot()
    assert (slot.number, slot.position_id) == (3, "p3")
    assert tab.has_unsaved_changes()


def test_open_folder_opens_the_spread_folder(window, monkeypatch):
    tab = saved_tab(window)
    opened = []
    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.spread_tab.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )

    tab.open_folder_action.trigger()

    assert opened == [str(tab.spread_path)]


def test_a_folder_that_will_not_open_says_so(window, monkeypatch):
    tab = saved_tab(window)
    shown = []
    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.spread_tab.QDesktopServices.openUrl", lambda _url: False
    )
    monkeypatch.setattr(window.toast, "show_message", shown.append)

    tab.open_folder_action.trigger()

    assert shown == [SPREADS["open_folder_failed"]]


def ring_of_slots(count, radius):
    """A spread of count positions on a circle, radius in card widths"""
    return Spread(
        positions=tuple(
            Position(
                id=f"p{index + 1}",
                x=radius * math.cos(2 * math.pi * index / count),
                y=radius * math.sin(2 * math.pi * index / count),
            )
            for index in range(count)
        )
    )


def in_view(tab):
    visible = tab.view.mapToScene(tab.view.viewport().rect()).boundingRect()
    return [slot for slot in tab.slots() if visible.contains(slot.sceneBoundingRect())]


def test_a_ring_too_wide_for_min_zoom_opens_with_every_slot_in_view(qtbot, tmp_path):
    tab = make_tab(qtbot, ring_of_slots(78, 27.5), tmp_path)

    qtbot.waitUntil(lambda: tab.view.transform().m11() < 1.0)

    assert len(in_view(tab)) == 78


def test_a_layout_past_min_zoom_can_be_zoomed_out_by_hand_until_it_fits(qtbot):
    tab = make_tab(qtbot, ring_of_slots(78, 27.5))
    tab.on_reset_view()

    for _ in range(40):
        before = tab.view.transform().m11()
        if not tab.can_zoom("out"):
            break
        tab.zoom("out")
        assert tab.view.transform().m11() < before

    assert not tab.can_zoom("out")
    tab.on_reset_view()
    tab.view.zoom_by_from_center(0.001)
    assert len(in_view(tab)) == 78


def test_a_small_layout_stops_at_min_zoom(qtbot):
    tab = make_tab(qtbot, ring_of_slots(4, 1))

    tab.view.zoom_by_from_center(0.001)

    assert tab.view.transform().m11() == pytest.approx(MIN_ZOOM)
    assert not tab.can_zoom("out")
