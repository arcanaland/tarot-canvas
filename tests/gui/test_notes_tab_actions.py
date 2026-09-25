"""The Notes tab acts on the note: one action set, inline rename, a delete that can be undone."""

import os

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QStyleOptionViewItem,
)

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
from tests.conftest import MINIMAL_DECK_PATH


@pytest.fixture
def no_dialogs(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a dialog opened")

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(refuse))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(refuse))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(refuse))


def cards():
    deck = TarotDeck(str(MINIMAL_DECK_PATH))
    return deck, [c for c in deck.get_all_cards() if c.get("image")]


def open_card_view(qtbot, *filenames, show=False):
    """A card view on a card holding `filenames`, oldest first, with the Notes tab raised."""
    deck, found = cards()
    card = found[0]
    tab = CardViewTab(card=card, deck=deck)
    qtbot.addWidget(tab)

    from tarot_canvas.models import notes as notes_model

    card_dir = notes_model.notes_base() / card["id"]
    paths = []
    for offset, name in enumerate(filenames):
        card_dir.mkdir(parents=True, exist_ok=True)
        path = card_dir / name
        path.write_text(f"# {path.stem}\n\nbody of {name}\n", encoding="utf-8")
        os.utime(path, (1_700_000_000 + offset, 1_700_000_000 + offset))
        paths.append(path)

    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()
    tab.show_notes_tab()

    if show:
        tab.resize(900, 700)
        with qtbot.waitActive(tab):
            tab.show()
            tab.activateWindow()
    return tab, card, paths


def row_of(notes, path):
    return notes.list_model.index_for_path(str(path))


def names(directory):
    return sorted(p.name for p in directory.iterdir())


def focus(qtbot, widget):
    widget.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is widget)


# -- the list page -------------------------------------------------------


def test_enter_on_the_highlighted_row_opens_it(qtbot, notes_base, no_dialogs):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md")
    notes = tab.notes_tab
    notes.list_view.setCurrentIndex(row_of(notes, path))

    qtbot.keyClick(notes.list_view, Qt.Key.Key_Return)

    assert notes.stack.currentWidget() is notes.editor_page
    assert notes.current_file_path == str(path)


def test_an_empty_card_shows_the_placeholder_whose_button_starts_a_note(
    qtbot, notes_base, no_dialogs
):
    tab, _, _ = open_card_view(qtbot)
    notes = tab.notes_tab
    placeholder = notes.empty_page.placeholder

    assert notes.stack.currentWidget() is notes.empty_page

    placeholder.helpful_button.click()

    assert notes.stack.currentWidget() is notes.editor_page
    assert notes.pending_path is not None


# -- one action set in three places -------------------------------------


def test_right_clicking_a_row_opens_the_menu_on_that_row(qtbot, notes_base):
    tab, _, (older, newer) = open_card_view(
        qtbot, "1700000000_Older.md", "1700000001_Newer.md", show=True
    )
    notes = tab.notes_tab
    rect = notes.list_view.visualRect(row_of(notes, older))

    notes.list_view.customContextMenuRequested.emit(rect.center())

    assert notes.note_menu.isVisible()
    assert notes.menu_target == str(older)
    notes.note_menu.hide()


def row_option(view, index):
    option = QStyleOptionViewItem()
    view.initViewItemOption(option)
    option.rect = view.visualRect(index)
    return option


def test_clicking_a_rows_menu_button_opens_the_menu_and_not_the_note(qtbot, notes_base):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md", show=True)
    notes = tab.notes_tab
    index = row_of(notes, path)
    button = notes.row_delegate._layout(row_option(notes.list_view, index)).menu

    qtbot.mouseClick(notes.list_view.viewport(), Qt.MouseButton.LeftButton, pos=button.center())

    assert notes.note_menu.isVisible()
    assert notes.menu_target == str(path)
    assert notes.stack.currentWidget() is notes.list_page
    notes.note_menu.hide()


def test_the_menu_acts_on_its_row_not_on_the_selected_one(qtbot, notes_base, no_dialogs):
    tab, card, (older, newer) = open_card_view(qtbot, "1700000000_Older.md", "1700000001_Newer.md")
    notes = tab.notes_tab
    notes.list_view.setCurrentIndex(row_of(notes, newer))

    notes.show_note_menu(str(older), notes.list_view.mapToGlobal(notes.list_view.rect().center()))
    notes.delete_action.trigger()
    notes.note_menu.hide()

    assert not older.exists()
    assert newer.exists()


def test_the_menu_forgets_its_row_once_closed(qtbot, notes_base):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md")
    notes = tab.notes_tab

    notes.show_note_menu(str(path), notes.list_view.mapToGlobal(notes.list_view.rect().center()))
    notes.note_menu.hide()

    qtbot.waitUntil(lambda: notes.menu_target is None)


def test_open_from_the_menu_opens_the_note(qtbot, notes_base, no_dialogs):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md")
    notes = tab.notes_tab

    notes.show_note_menu(str(path), notes.list_view.mapToGlobal(notes.list_view.rect().center()))
    notes.open_action.trigger()
    notes.note_menu.hide()

    assert notes.stack.currentWidget() is notes.editor_page
    assert notes.current_file_path == str(path)


# -- renaming in place -----------------------------------------------------


def test_f2_then_a_name_then_enter_renames_the_file_and_keeps_its_timestamp(
    qtbot, notes_base, no_dialogs
):
    tab, card, (path,) = open_card_view(qtbot, "1700000000_Old.md", show=True)
    notes = tab.notes_tab
    notes.list_view.setCurrentIndex(row_of(notes, path))
    focus(qtbot, notes.list_view)

    qtbot.keyClick(notes.list_view, Qt.Key.Key_F2)
    editor = QApplication.focusWidget()
    assert isinstance(editor, QLineEdit)
    assert editor.text() == "Old"
    qtbot.keyClicks(editor, "Lyrics")
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    qtbot.waitUntil(lambda: names(path.parent) == ["1700000000_Lyrics.md"])
    assert notes.list_model.index(0, 0).data() == "Lyrics"


def test_rename_from_the_editor_menu_selects_the_name_field(qtbot, notes_base, no_dialogs):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md", show=True)
    notes = tab.notes_tab
    notes.open_note_path(str(path))

    notes.editor_menu.aboutToShow.emit()
    notes.rename_action.trigger()

    qtbot.waitUntil(notes.note_title.hasFocus)
    assert notes.note_title.selectedText() == "Lyrics"


# -- the keys belong to the list ----------------------------------------


def test_del_in_the_list_deletes_the_highlighted_row(qtbot, notes_base, no_dialogs):
    tab, _, (older, newer) = open_card_view(
        qtbot, "1700000000_Older.md", "1700000001_Newer.md", show=True
    )
    notes = tab.notes_tab
    notes.list_view.setCurrentIndex(row_of(notes, older))
    focus(qtbot, notes.list_view)

    qtbot.keyClick(notes.list_view, Qt.Key.Key_Delete)

    assert not older.exists()
    assert newer.exists()


def test_del_in_the_editor_deletes_a_character_not_the_note(qtbot, notes_base, no_dialogs):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md", show=True)
    notes = tab.notes_tab
    notes.open_note_path(str(path))
    focus(qtbot, notes.note_editor)
    notes.note_editor.moveCursor(QTextCursor.MoveOperation.Start)
    before = notes.note_editor.toPlainText()

    qtbot.keyClick(notes.note_editor, Qt.Key.Key_Delete)

    assert notes.note_editor.toPlainText() == before[1:]
    assert path.exists()
    assert notes.staged_delete is None


# -- deleting, undoably ----------------------------------------------------


def delete(notes, path):
    notes.show_note_menu(str(path), notes.list_view.mapToGlobal(notes.list_view.rect().center()))
    notes.delete_action.trigger()
    notes.note_menu.hide()


def staged(path):
    return path.with_name(path.name + ".deleted")


def test_a_delete_asks_nothing_and_takes_the_note_out_of_every_view(qtbot, notes_base, no_dialogs):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md")
    notes = tab.notes_tab

    delete(notes, path)

    assert staged(path).exists()
    assert not path.exists()
    assert notes.list_model.rowCount() == 0
    assert notes.stack.currentWidget() is notes.empty_page
    assert tab.overview_tab.notes_section.ghost.isVisibleTo(tab.overview_tab.notes_section)
    assert notes.message.isVisibleTo(notes)
    assert [b.defaultAction() for b in notes.message.action_buttons] == [notes.undo_action]


def test_undo_puts_the_note_back_byte_for_byte(qtbot, notes_base, no_dialogs):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md")
    notes = tab.notes_tab
    before = path.read_bytes()

    delete(notes, path)
    notes.undo_action.trigger()

    assert path.read_bytes() == before
    assert not staged(path).exists()
    assert notes.list_model.index_for_path(str(path)).isValid()
    assert notes.stack.currentWidget() is notes.list_page
    assert not notes.message.isVisibleTo(notes)
    assert tab.overview_tab.notes_section.list_view.model().rowCount() == 1


def test_dismissing_the_message_makes_the_delete_final(qtbot, notes_base, no_dialogs):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md")
    notes = tab.notes_tab

    delete(notes, path)
    notes.message.close_button.click()

    assert names(path.parent) == []


def test_a_second_delete_makes_the_first_final(qtbot, notes_base, no_dialogs):
    tab, _, (older, newer) = open_card_view(qtbot, "1700000000_Older.md", "1700000001_Newer.md")
    notes = tab.notes_tab

    delete(notes, older)
    delete(notes, newer)

    assert names(older.parent) == [staged(newer).name]
    assert notes.staged_delete == (str(newer), str(staged(newer)))


def test_changing_card_makes_the_delete_final(qtbot, notes_base, no_dialogs):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md")
    notes = tab.notes_tab
    deck, found = cards()

    delete(notes, path)
    tab.show_card(found[1], deck)

    assert names(path.parent) == []
    assert not notes.message.isVisibleTo(notes)


def test_quitting_makes_the_delete_final(qtbot, notes_base, no_dialogs):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md")

    delete(tab.notes_tab, path)
    QApplication.instance().aboutToQuit.emit()

    assert names(path.parent) == []


def test_closing_the_card_views_tab_makes_the_delete_final(qtbot, notes_base, no_dialogs):
    from tarot_canvas.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.new_card_view_tab()
    card_view = window.tab_widget.currentWidget()
    card_dir = notes_base / card_view.card["id"]
    card_dir.mkdir(parents=True)
    path = card_dir / "1700000000_Lyrics.md"
    path.write_text("# Lyrics\n\nbody\n", encoding="utf-8")
    card_view.notes_tab.load_card_notes(card_view.card)

    delete(card_view.notes_tab, path)
    window.close_tab(window.tab_widget.indexOf(card_view))

    assert names(card_dir) == []


def test_a_delete_from_the_editor_returns_to_the_list_and_keeps_what_was_typed(
    qtbot, notes_base, no_dialogs
):
    tab, _, (older, newer) = open_card_view(qtbot, "1700000000_Older.md", "1700000001_Newer.md")
    notes = tab.notes_tab
    notes.open_note_path(str(newer))
    notes.note_editor.moveCursor(QTextCursor.MoveOperation.End)
    qtbot.keyClicks(notes.note_editor, "typed")

    notes.editor_menu.aboutToShow.emit()
    notes.delete_action.trigger()
    notes.editor_menu.hide()

    assert notes.stack.currentWidget() is notes.list_page
    assert notes.current_file_path is None
    assert "typed" in staged(newer).read_text(encoding="utf-8")

    # Nothing brings the deleted file back behind Undo's back
    notes.save_if_modified()
    assert not newer.exists()


# -- silence on success ----------------------------------------------------


def test_export_copies_the_note_and_says_nothing(
    qtbot, notes_base, tmp_path, no_dialogs, monkeypatch
):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md")
    notes = tab.notes_tab
    target = tmp_path / "exported.md"
    offered = []

    def save_to(parent, caption, directory, filters):
        offered.append(directory)
        return str(target), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(save_to))

    notes.show_note_menu(str(path), notes.list_view.mapToGlobal(notes.list_view.rect().center()))
    notes.export_action.trigger()
    notes.note_menu.hide()

    assert target.read_bytes() == path.read_bytes()
    assert offered[0].endswith("Lyrics.md")


def test_save_is_enabled_only_while_there_is_something_to_save(qtbot, notes_base, no_dialogs):
    tab, _, (path,) = open_card_view(qtbot, "1700000000_Lyrics.md")
    notes = tab.notes_tab
    notes.open_note_path(str(path))
    assert not notes.save_button.isEnabled()

    notes.note_editor.moveCursor(QTextCursor.MoveOperation.End)
    qtbot.keyClicks(notes.note_editor, "typed")
    assert notes.save_button.isEnabled()

    notes.save_button.click()
    assert not notes.save_button.isEnabled()
    assert "typed" in path.read_text(encoding="utf-8")
