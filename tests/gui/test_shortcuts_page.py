from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QKeySequenceEdit,
    QLineEdit,
    QToolButton,
)

from tarot_canvas.settings import SHORTCUTS_PREFIX, get_settings
from tarot_canvas.ui import commands
from tarot_canvas.ui.commands import COMMANDS
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.windows.preferences_dialog import PreferencesDialog
from tarot_canvas.ui.windows.preferences_text import PREFERENCES_TEXT
from tarot_canvas.ui.windows.shortcuts_page import COMMAND_ROLE


def make_dialog(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    return dialog, dialog.shortcuts_page


def cell(page, command_id, column=1):
    return page.cells[command_id][0].index().siblingAtColumn(column)


def propose(page, command_id, key, column=1):
    page.propose(cell(page, command_id, column), QKeySequence(key))


def open_editor(page, command_id, column=1):
    index = page.proxy.mapFromSource(cell(page, command_id, column))
    page.tree.edit(index)
    editor = page.tree.indexWidget(index)
    assert isinstance(editor, QKeySequenceEdit)
    return editor


def stored_shortcuts():
    return [key for key in get_settings().allKeys() if key.startswith(SHORTCUTS_PREFIX)]


def visible_rows(page):
    """(group, [labels]) for every group the filter shows"""
    proxy = page.proxy
    rows = []
    for group_row in range(proxy.rowCount()):
        group = proxy.index(group_row, 0)
        labels = [proxy.index(row, 0, group).data() for row in range(proxy.rowCount(group))]
        rows.append((group.data(), labels))
    return rows


def test_the_tree_lists_every_command_with_a_key_of_its_own_once(qtbot):
    _dialog, page = make_dialog(qtbot)
    listed = []
    for group_row in range(page.model.rowCount()):
        group = page.model.item(group_row, 0)
        listed += [group.child(row, 0).data(COMMAND_ROLE) for row in range(group.rowCount())]

    assert sorted(listed) == sorted(command.id for command in COMMANDS if not command.shows)


def test_a_command_shows_its_label_and_keys(qtbot):
    _dialog, page = make_dialog(qtbot)

    assert page.model.itemFromIndex(cell(page, "window.new_canvas", 0)).text() == "New Canvas"
    assert page.model.itemFromIndex(cell(page, "card_image.first", 0)).text() == "First Card"
    assert cell(page, "card_image.previous", 1).data() == "PgUp"
    assert cell(page, "card_image.previous", 2).data() == "Backspace"


def test_searching_a_key_leaves_only_its_command(qtbot):
    _dialog, page = make_dialog(qtbot)

    page.search.setText("ctrl+]")

    assert visible_rows(page) == [(PREFERENCES_TEXT["shortcuts_canvas"], ["Bring to Front"])]


def test_a_fixed_command_is_listed_greyed_and_not_editable(qtbot):
    _dialog, page = make_dialog(qtbot)

    flags = cell(page, "card_image.next_or_pan").flags()

    assert cell(page, "card_image.next_or_pan").data() == "Right"
    assert not flags & Qt.ItemFlag.ItemIsEditable
    assert not flags & Qt.ItemFlag.ItemIsEnabled


def test_a_key_another_command_holds_is_refused_naming_it(qtbot):
    dialog, page = make_dialog(qtbot)
    dialog.show()

    propose(page, "canvas.summon", "Ctrl+N")

    assert page.keys["canvas.summon"] == ("D",)
    assert cell(page, "canvas.summon").data() == "D"
    assert not page.message.isHidden()
    assert "New Canvas" in page.message.label.text()

    propose(page, "canvas.summon", "S")
    assert page.message.isHidden()


def test_a_bare_letter_is_refused_for_a_window_command(qtbot):
    dialog, page = make_dialog(qtbot)
    dialog.show()

    propose(page, "window.find_card", "P")

    assert page.keys["window.find_card"] == ("Ctrl+P",)
    assert not page.message.isHidden()


def test_a_key_freed_on_the_page_can_be_taken_before_apply(qtbot):
    _dialog, page = make_dialog(qtbot)

    propose(page, "canvas.flip", "D", column=2)
    assert page.keys["canvas.flip"] == ("R",)

    propose(page, "canvas.summon", "S")
    propose(page, "canvas.flip", "D", column=2)
    # The art's D never fires while a canvas's does
    assert page.keys["canvas.flip"] == ("R", "D")
    assert page.keys["card_image.random"] == ("D",)


def test_a_key_typed_into_the_editor_is_taken(qtbot, qtlog):
    dialog, page = make_dialog(qtbot)
    dialog.show()
    dialog.activateWindow()
    qtbot.waitActive(dialog)
    dialog.page_list.setCurrentRow(3)

    editor = open_editor(page, "canvas.summon")
    qtbot.waitUntil(editor.hasFocus)
    qtbot.keyClick(editor, Qt.Key.Key_S)

    assert page.keys["canvas.summon"] == ("S",)
    assert page.tree.state() is not QAbstractItemView.State.EditingState
    # Finished once, not again as it closes
    assert not [record for record in qtlog.records if "does not belong" in record.message]

    # Esc is a key to record, not a way out
    editor = open_editor(page, "canvas.summon", column=2)
    qtbot.keyClick(editor, Qt.Key.Key_Escape)
    assert page.keys["canvas.summon"] == ("S",)
    assert not page.message.isHidden()
    assert dialog.isVisible()


def test_the_editors_clear_button_clears_the_cell(qtbot):
    dialog, page = make_dialog(qtbot)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog.page_list.setCurrentRow(3)

    editor = open_editor(page, "canvas.summon")
    clear = editor.findChild(QLineEdit).findChild(QToolButton)
    qtbot.waitUntil(clear.isVisible)
    qtbot.mouseClick(clear, Qt.MouseButton.LeftButton)

    assert page.keys["canvas.summon"] == ()
    assert page.tree.state() is not QAbstractItemView.State.EditingState


def test_changing_a_key_offers_apply_and_changing_it_back_withdraws_it(qtbot):
    dialog, page = make_dialog(qtbot)
    assert not dialog.apply_button.isEnabled()

    propose(page, "canvas.summon", "S")
    assert dialog.apply_button.isEnabled()

    propose(page, "canvas.summon", "D")
    assert not dialog.apply_button.isEnabled()


def test_clearing_a_key_stores_no_key(qtbot):
    dialog, page = make_dialog(qtbot)

    page.propose(cell(page, "canvas.summon"), QKeySequence())
    dialog.apply_settings()

    assert commands.keys_for("canvas.summon") == []


def test_an_unedited_command_keeps_every_key_and_an_edited_one_keeps_two(qtbot):
    dialog, page = make_dialog(qtbot)
    all_keys = commands.default_keys("window.copy_card")
    assert len(all_keys) > 2

    propose(page, "canvas.summon", "S")
    dialog.apply_settings()
    assert commands.keys_for("window.copy_card") == all_keys
    assert stored_shortcuts() == [SHORTCUTS_PREFIX + "canvas.summon"]

    propose(page, "window.copy_card", "Ctrl+Shift+C", column=2)
    dialog.apply_settings()
    assert commands.keys_for("window.copy_card") == [all_keys[0], QKeySequence("Ctrl+Shift+C")]


def test_defaults_then_apply_stores_no_shortcut(qtbot):
    get_settings().setValue(SHORTCUTS_PREFIX + "canvas.summon", ["S"])
    dialog, page = make_dialog(qtbot)
    assert page.keys["canvas.summon"] == ("S",)

    dialog.restore_defaults()
    dialog.apply_settings()

    assert stored_shortcuts() == []


def test_applying_a_key_rekeys_an_open_window_and_its_tooltips(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    tab = window.new_canvas_tab()
    window.activateWindow()
    qtbot.waitActive(window)
    tab.view.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is tab.view)
    summoned = []
    tab.commands["canvas.summon"].triggered.connect(lambda: summoned.append(True))

    commands.store_keys("canvas.summon", ["S"])
    commands.store_keys("card_image.first", ["G"])
    commands.apply_shortcuts()

    qtbot.keyClick(tab.view, Qt.Key.Key_D)
    assert summoned == []
    qtbot.keyClick(tab.view, Qt.Key.Key_S)
    assert summoned == [True]
    assert tab.commands["canvas.summon"].toolTip() == "Summon a random card (S)"
    assert window.go_actions["first"].text() == "&First Card\tG"

    qtbot.wait(1100)
