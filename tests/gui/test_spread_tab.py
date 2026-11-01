import pytest
from PyQt6.QtCore import QModelIndex, QPoint, QPointF, QRect, QSize, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QMessageBox, QStyleOptionViewItem, QToolButton

from tarot_canvas.models import spreads
from tarot_canvas.ui import commands
from tarot_canvas.ui.canvas.slot_item import SlotItem
from tarot_canvas.ui.canvas.spread_pane import MeaningRole, NumberRole
from tarot_canvas.ui.card_transfer import card_mime_data, copy_card_to_clipboard
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


def test_clearing_the_name_field_goes_back_to_untitled(qtbot):
    tab = make_tab(qtbot)
    tab.pane.name_edit.setText("Named")

    tab.pane.name_edit.clear()

    assert tab.rename_text() == ""
    assert tab.display_name() == SPREADS["untitled"]


# -- ways in


# -- keeping it


def test_the_toolbar_has_no_save(qtbot):
    tab = make_tab(qtbot)

    assert "window.save" not in [action.objectName() for action in tab.toolbar.actions()]


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


def test_every_write_announces_itself(qtbot, spreads_base):
    from tarot_canvas.models.spread_events import spread_events

    tab = make_tab(qtbot)
    with qtbot.waitSignal(spread_events().spreads_changed, timeout=500):
        tab.save()
    tab.rename("Again")
    with qtbot.waitSignal(spread_events().spreads_changed, timeout=500):
        tab.save()


# -- unsaved changes


# -- opening it


def test_the_pane_starts_beside_the_canvas(qtbot):
    tab = make_tab(qtbot)
    assert tab.splitter.orientation() == Qt.Orientation.Horizontal
    assert tab.splitter.widget(0) is tab.canvas_area
    assert tab.splitter.widget(1) is tab.pane


# -- the pane's menu


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
