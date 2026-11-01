import pytest
from PyQt6.QtCore import QPointF, QSize, Qt
from PyQt6.QtWidgets import QApplication, QToolButton

from tarot_canvas.models import spreads
from tarot_canvas.models.spreads import Position, Spread
from tarot_canvas.ui.canvas.slot_item import SlotItem
from tarot_canvas.ui.card_transfer import card_mime_data, copy_card_to_clipboard
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import SPREADS
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.spread_tab import AUTOSAVE_MS, SpreadTab

PAST_THE_TIMER = AUTOSAVE_MS + 200
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


def listed(tab):
    rows = tab.pane.slot_list
    return [rows.item(row).text() for row in range(rows.count())]


def centre(slot):
    return slot.pos() + slot.boundingRect().center()


def menu_action(menu, words):
    return next(action for action in menu.actions() if words in action.text())


@pytest.fixture
def window(qtbot, spreads_base):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


# -- slots


def test_each_added_slot_takes_the_next_number_and_id(qtbot):
    tab = make_tab(qtbot)
    slots = [tab.commands["canvas.add_slot"].trigger() or tab.slots()[-1] for _ in range(3)]

    assert [slot.number for slot in slots] == [1, 2, 3]
    assert [slot.position_id for slot in slots] == ["p1", "p2", "p3"]


def test_the_toolbar_adds_slots_and_has_no_summon_or_flip(qtbot):
    tab = make_tab(qtbot)
    ids = [action.objectName() for action in tab.toolbar.actions()]

    assert "canvas.add_slot" in ids
    assert "canvas.rotate" in ids
    assert "canvas.summon" not in ids
    assert "canvas.flip" not in ids
    assert not {"canvas.summon", "canvas.flip"} & tab.commands.keys()


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


def test_make_first_moves_the_last_slot_to_one_and_keeps_its_id(qtbot):
    tab = make_tab(qtbot)
    first, second, third = add_slots(tab, 3)
    select(tab, third)

    menu = tab.build_card_menu(third)
    number = menu_action(menu, SPREADS["number"]).menu()
    menu_action(number, SPREADS["make_first"]).trigger()

    assert tab.slots() == (third, first, second)
    assert [slot.number for slot in tab.slots()] == [1, 2, 3]
    assert third.position_id == "p3"


def test_moving_a_slot_earlier_and_later_swaps_its_neighbour(qtbot):
    tab = make_tab(qtbot)
    first, second, third = add_slots(tab, 3)

    tab.move_slot(second, 0)
    assert tab.slots() == (second, first, third)
    tab.move_slot(second, 1)
    assert tab.slots() == (first, second, third)


def test_a_slot_cannot_move_past_either_end(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)

    number = menu_action(tab.build_card_menu(first), SPREADS["number"]).menu()
    assert not menu_action(number, SPREADS["move_earlier"]).isEnabled()
    assert not menu_action(number, SPREADS["make_first"]).isEnabled()
    assert menu_action(number, SPREADS["move_later"]).isEnabled()

    number = menu_action(tab.build_card_menu(second), SPREADS["number"]).menu()
    assert not menu_action(number, SPREADS["move_later"]).isEnabled()


def test_a_slot_menu_has_the_slot_entries_in_order(qtbot):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)

    menu = tab.card_menu(centre(slot))

    assert [action.isSeparator() or action.text() for action in menu.actions()] == [
        SPREADS["edit_label"],
        SPREADS["edit_meaning"],
        SPREADS["number"],
        True,
        tab.commands["canvas.rotate"].text(),
        True,
        tab.commands["canvas.delete"].text(),
    ]


def test_editing_and_numbering_need_a_single_slot(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    first.setSelected(True)
    second.setSelected(True)

    menu = tab.build_card_menu(first)

    for words in ("edit_label", "edit_meaning", "number"):
        assert not menu_action(menu, SPREADS[words]).isEnabled()


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


def test_typing_a_label_changes_the_slot_and_its_face(qtbot):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)
    before = image(slot)

    qtbot.keyClicks(tab.pane.label_edit, "Past")

    assert slot.label == "Past"
    assert image(slot) != before


def test_typing_a_meaning_changes_the_slot(qtbot):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)

    qtbot.keyClicks(tab.pane.meaning_edit, "Before")

    assert slot.meaning == "Before"


def test_selecting_a_slot_shows_its_fields_and_keeps_the_other_slots_own(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    select(tab, first)
    tab.pane.label_edit.setText("Past")
    select(tab, second)
    assert tab.pane.label_edit.text() == ""

    select(tab, first)

    assert tab.pane.label_edit.text() == "Past"
    assert second.label == ""


def test_with_nothing_or_several_selected_the_pane_lists_every_slot(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    first.set_label("Past")

    tab.scene.clearSelection()
    rows = [SPREADS["slot_row"].format(number=1, label="Past")]
    rows.append(SPREADS["slot_row"].format(number=2, label=""))
    assert listed(tab) == rows
    assert not tab.pane.slot_list.isHidden()
    assert tab.pane.slot_editor.isHidden()

    first.setSelected(True)
    assert tab.pane.slot_list.isHidden()

    second.setSelected(True)
    assert listed(tab) == rows
    assert not tab.pane.slot_list.isHidden()


def test_clicking_a_row_selects_its_slot(qtbot):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    tab.scene.clearSelection()

    tab.pane.slot_list.itemClicked.emit(tab.pane.slot_list.item(1))

    assert tab.selected_cards() == [second]


def test_edit_label_reopens_a_collapsed_pane(qtbot):
    tab = make_tab(qtbot)
    add_slots(tab, 1)
    tab.pane.set_open(False)
    assert not tab.pane.is_open()
    assert not tab.pane_action.isChecked()

    tab.edit_label()

    assert tab.pane.is_open()
    assert tab.pane_action.isChecked()


def test_the_toolbar_toggle_collapses_the_pane(qtbot):
    tab = make_tab(qtbot)
    assert tab.pane.is_open()

    tab.pane_action.trigger()
    assert not tab.pane.is_open()

    tab.pane_action.trigger()
    assert tab.pane.is_open()


def test_a_blank_source_row_is_not_kept(qtbot):
    tab = make_tab(qtbot)
    tab.pane.add_source_row()
    tab.pane.add_source_row().edits["author"].setText("Someone")

    assert tab.pane.sources() == ({"author": "Someone"},)


def test_removing_a_source_row_drops_it(qtbot):
    tab = make_tab(qtbot)
    row = tab.pane.add_source_row({"url": "a"})
    tab.pane.add_source_row({"url": "b"})

    row.remove_button.click()

    assert tab.pane.sources() == ({"url": "b"},)


def test_a_source_keeps_keys_the_pane_does_not_show(qtbot):
    tab = make_tab(qtbot)
    row = tab.pane.add_source_row({"url": "a", "x_seen": "2026"})
    row.edits["url"].setText("b")

    assert tab.pane.sources() == ({"url": "b", "x_seen": "2026"},)


# -- the label


def test_the_tab_label_follows_the_name(qtbot):
    tab = make_tab(qtbot)
    assert tab.tab_title() == SPREADS["untitled"]

    with qtbot.waitSignal(tab.tab_label_changed):
        tab.pane.name_edit.setText("The Horseshoe")

    assert tab.tab_title() == "The Horseshoe"


def test_renaming_the_tab_sets_the_name(window, qtbot, monkeypatch):
    tab = window.new_spread_tab()
    index = window.tab_widget.indexOf(tab)
    tab.pane.set_name("Old")
    offered = []

    def answer(*_, text):
        offered.append(text)
        return "New", True

    monkeypatch.setattr("tarot_canvas.ui.main_window.QInputDialog.getText", answer)
    window.show_tab_rename_dialog(index)

    assert offered == ["Old"]
    assert tab.pane.name() == "New"
    assert window.tab_widget.tabText(index) == "New"


# -- ways in


def test_new_spread_is_in_the_file_and_new_tab_menus_after_new_canvas(window):
    file_menu = window.menuBar().actions()[0].menu()
    actions = file_menu.actions()
    assert actions[actions.index(window.new_canvas_action) + 1] is window.new_spread_action

    new_tab_menu = next(
        button.menu()
        for button in window.findChildren(QToolButton)
        if button.menu() is not None and window.new_canvas_action in button.menu().actions()
    )
    actions = new_tab_menu.actions()
    assert actions[actions.index(window.new_canvas_action) + 1] is window.new_spread_action


def test_new_spread_opens_a_spread_tab(window):
    window.new_spread_action.trigger()

    tab = window.tab_widget.currentWidget()
    assert isinstance(tab, SpreadTab)
    assert window.tab_widget.tabText(window.tab_widget.currentIndex()) == SPREADS["untitled"]


# -- keeping it


def test_a_plain_canvas_has_no_save(qtbot):
    tab = CanvasTab()
    qtbot.addWidget(tab)

    assert "canvas.save" not in tab.commands
    assert "canvas.save" not in [action.objectName() for action in tab.toolbar.actions()]
    assert "canvas.save" not in [action.objectName() for action in tab.actions()]


def test_ctrl_s_writes_card_widths_about_the_layout_centre(qtbot, spreads_base):
    tab = make_tab(qtbot)
    tab.add_next_slot(QPointF(100, 50))
    second = tab.add_next_slot(QPointF(100 + 2 * UNIT, 50 + UNIT))
    tab.scene.clearSelection()
    second.setSelected(True)
    tab.on_rotate_card()

    tab.commands["canvas.save"].trigger()

    assert tab.spread_path.parent == spreads_base
    first, second = spreads.load(tab.spread_path).positions
    assert (first.x, first.y) == (-1.0, -0.5)
    assert (second.x, second.y) == (1.0, 0.5)
    assert (first.rotation, second.rotation) == (0.0, 90.0)
    assert first.z < second.z


def test_save_is_disabled_after_the_first(qtbot, spreads_base):
    tab = make_tab(qtbot)
    tab.on_save()
    folder = tab.spread_path

    assert not tab.commands["canvas.save"].isEnabled()
    tab.on_save()
    assert tab.spread_path == folder
    assert len(list(spreads_base.iterdir())) == 1


def test_nothing_is_written_before_the_first_save(qtbot, spreads_base):
    tab = make_tab(qtbot)
    add_slots(tab, 1)
    tab.pane.name_edit.setText("Nope")

    assert not tab.autosave_timer.isActive()
    assert not spreads_base.exists()


def test_an_edit_after_the_first_save_lands_after_the_timer(qtbot, spreads_base):
    tab = make_tab(qtbot)
    tab.on_save()

    tab.pane.name_edit.setText("The Horseshoe")
    assert spreads.load(tab.spread_path).name == ""

    qtbot.wait(PAST_THE_TIMER)
    assert spreads.load(tab.spread_path).name == "The Horseshoe"


@pytest.mark.parametrize(
    "change",
    [
        lambda tab: tab.add_next_slot(),
        lambda tab: tab.on_rotate_card(),
        lambda tab: tab.on_delete_card(),
        lambda tab: tab.on_bring_to_front(),
        lambda tab: tab.on_send_to_back(),
        lambda tab: tab.move_slot(tab.slots()[1], 0),
        lambda tab: tab.pane.usage_edit.setPlainText("Use it"),
        lambda tab: tab.pane.label_edit.setText("Past"),
        lambda tab: tab.pane.meaning_edit.setPlainText("Before"),
        lambda tab: tab.pane.add_source_row().edits["url"].setText("a"),
    ],
)
def test_every_kind_of_change_arms_the_timer(qtbot, spreads_base, change):
    tab = make_tab(qtbot)
    first, _ = add_slots(tab, 2)
    select(tab, first)
    tab.on_save()
    assert not tab.autosave_timer.isActive()

    change(tab)

    assert tab.autosave_timer.isActive()
    tab.autosave_timer.stop()


def test_a_drag_arms_the_timer_when_it_ends(qtbot, spreads_base):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)
    tab.on_save()
    tab.autosave_timer.stop()

    slot.begin_drag()
    slot.end_drag()

    assert tab.autosave_timer.isActive()
    tab.autosave_timer.stop()


def test_a_press_with_no_drag_arms_nothing(qtbot, spreads_base):
    tab = make_tab(qtbot)
    (slot,) = add_slots(tab, 1)
    tab.on_save()

    slot.end_drag()

    assert not tab.autosave_timer.isActive()


def test_an_arrangement_from_the_align_menu_arms_the_timer(qtbot, spreads_base, monkeypatch):
    tab = make_tab(qtbot)
    first, second = add_slots(tab, 2)
    first.setSelected(True)
    second.setSelected(True)
    tab.on_save()

    monkeypatch.setattr(
        "tarot_canvas.ui.tabs.canvas_tab.QMenu.exec",
        lambda menu, *_: menu.triggered.emit(menu.actions()[0]),
    )
    tab.on_align_cards()

    assert tab.autosave_timer.isActive()
    tab.autosave_timer.stop()


def test_closing_the_tab_writes_what_is_pending(window, spreads_base):
    tab = window.new_spread_tab()
    tab.on_save()
    tab.pane.name_edit.setText("Kept")

    window.close_tab(window.tab_widget.indexOf(tab))

    assert not tab.autosave_timer.isActive()
    assert spreads.load(tab.spread_path).name == "Kept"


def test_quitting_writes_what_is_pending(qtbot, spreads_base):
    tab = make_tab(qtbot)
    tab.on_save()
    tab.pane.name_edit.setText("Kept")

    QApplication.instance().aboutToQuit.emit()

    assert spreads.load(tab.spread_path).name == "Kept"


def test_a_failed_write_keeps_the_tab_unsaved_and_leaves_no_folder(
    qtbot, spreads_base, monkeypatch
):
    def fail(*_):
        raise OSError("disk full")

    monkeypatch.setattr(spreads, "save", fail)
    tab = make_tab(qtbot)

    tab.on_save()

    assert tab.spread_path is None
    assert tab.commands["canvas.save"].isEnabled()
    assert list(spreads_base.iterdir()) == []


def test_every_write_announces_itself(qtbot, spreads_base):
    from tarot_canvas.models.spread_events import spread_events

    tab = make_tab(qtbot)
    with qtbot.waitSignal(spread_events().spreads_changed, timeout=500):
        tab.on_save()
    tab.pane.name_edit.setText("Again")
    with qtbot.waitSignal(spread_events().spreads_changed, timeout=PAST_THE_TIMER):
        pass


# -- opening it


def stored_spread():
    return Spread(
        name="The Horseshoe",
        usage="Left to right",
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
    assert tab.pane.name() == "The Horseshoe"
    assert tab.pane.usage() == "Left to right"
    assert tab.pane.sources() == ({"author": "Someone"},)
    assert window.tab_widget.tabText(window.tab_widget.indexOf(tab)) == "The Horseshoe"


def test_a_reopened_slot_does_not_animate_in(window, spreads_base):
    tab = window.open_spread(stored(spreads_base))

    for slot in tab.slots():
        assert not slot.isSelected()
        assert slot.motion.orient_lag == 0.0
        assert slot.motion.at_rest()


def test_opening_writes_nothing_and_arms_nothing(window, spreads_base, qtbot):
    path = stored(spreads_base)
    file = path / "spread.toml"
    before = file.stat().st_mtime_ns

    tab = window.open_spread(path)

    assert not tab.autosave_timer.isActive()
    qtbot.wait(PAST_THE_TIMER)
    assert file.stat().st_mtime_ns == before
    assert not tab.commands["canvas.save"].isEnabled()


def test_opening_twice_raises_the_tab(window, spreads_base):
    path = stored(spreads_base)
    tab = window.open_spread(path)
    window.new_canvas_tab()
    count = window.tab_widget.count()

    assert window.open_spread(path) is tab
    assert window.tab_widget.count() == count
    assert window.tab_widget.currentWidget() is tab


def test_an_unreadable_spread_opens_nothing(window, spreads_base):
    path = spreads_base / "1000"
    path.mkdir(parents=True)
    (path / "spread.toml").write_text("name = [")
    count = window.tab_widget.count()

    assert window.open_spread(path) is None
    assert window.tab_widget.count() == count


def test_saving_a_reopened_spread_keeps_its_unknown_keys_and_order(window, spreads_base, qtbot):
    tab = window.open_spread(stored(spreads_base))

    tab.pane.name_edit.setText("Renamed")
    qtbot.wait(PAST_THE_TIMER)

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
    tab.on_save()
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
