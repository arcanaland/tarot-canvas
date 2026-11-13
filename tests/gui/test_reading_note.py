"""A saved reading's one note: always open, written a moment after each edit."""

import re

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from tarot_canvas.models import readings
from tarot_canvas.ui.canvas.saved_canvas import AUTOSAVE_MS
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.strings import READINGS


@pytest.fixture(autouse=True)
def discard_on_teardown(monkeypatch):
    """A window left with unsaved work would otherwise wait on a dialog as it closes"""
    monkeypatch.setattr(
        "tarot_canvas.ui.main_window.QMessageBox.warning",
        lambda *_: QMessageBox.StandardButton.Discard,
    )


@pytest.fixture
def window(qtbot, stub_deck_manager, spreads_base, notes_base):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def save_a_canvas(window, deck):
    """A canvas with a card, just saved as a reading"""
    tab = window.new_canvas_tab()
    card = next(card for card in deck.cards if card.default_image())
    tab.add_specific_card(card, card_deck=deck)
    window.tab_widget.setCurrentWidget(tab)
    window.update_save_action()
    window.save_action.trigger()
    return tab


@pytest.fixture
def saved_tab(window, minimal_deck):
    return save_a_canvas(window, minimal_deck)


@pytest.fixture
def focused(qtbot, window, minimal_deck):
    """A canvas saved in a window that has focus, once its pane is showing"""
    window.show()
    window.activateWindow()
    qtbot.waitActive(window)
    tab = save_a_canvas(window, minimal_deck)
    qtbot.waitUntil(tab.saved_reading.pane.isVisible)
    return tab


def notes_in(path):
    return sorted(path.glob("*.md"))


def test_a_new_reading_shows_an_empty_editor_and_writes_no_note(saved_tab, notes_base):
    note = saved_tab.saved_reading.pane.note

    assert note.editor.isVisibleTo(saved_tab)
    assert note.editor.placeholderText() == READINGS["notes_hint"]
    assert note.editor.toPlainText() == ""
    assert notes_in(saved_tab.reading_path) == []


def test_typing_writes_one_note_and_leaves_the_reading_alone(qtbot, saved_tab, notes_base):
    path = saved_tab.reading_path
    reading_file = path / readings.READING_FILE
    written = reading_file.stat().st_mtime_ns

    qtbot.keyClicks(saved_tab.saved_reading.pane.note.editor, "The tower, again")
    qtbot.waitUntil(lambda: len(notes_in(path)) == 1, timeout=AUTOSAVE_MS * 3)

    (note,) = notes_in(path)
    assert re.fullmatch(r"\d+\.md", note.name)
    assert note.read_text(encoding="utf-8") == "The tower, again"
    assert reading_file.stat().st_mtime_ns == written
    assert not notes_base.exists()


def test_blank_typing_writes_no_note(qtbot, saved_tab):
    qtbot.keyClicks(saved_tab.saved_reading.pane.note.editor, "   ")
    qtbot.wait(AUTOSAVE_MS * 2)

    assert notes_in(saved_tab.reading_path) == []


def test_closing_the_tab_at_once_keeps_what_was_typed(qtbot, window, saved_tab):
    path = saved_tab.reading_path

    qtbot.keyClicks(saved_tab.saved_reading.pane.note.editor, "Last thought")
    window.close_tab(window.tab_widget.indexOf(saved_tab))

    (note,) = notes_in(path)
    assert note.read_text(encoding="utf-8") == "Last thought"


def test_emptying_the_note_empties_its_file(qtbot, window, saved_tab):
    path = saved_tab.reading_path
    editor = saved_tab.saved_reading.pane.note.editor
    qtbot.keyClicks(editor, "Gone soon")
    saved_tab.flush_pending_edits()

    editor.selectAll()
    qtbot.keyClick(editor, Qt.Key.Key_Delete)
    saved_tab.flush_pending_edits()

    (note,) = notes_in(path)
    assert note.read_text(encoding="utf-8") == ""


def test_a_reopened_reading_shows_its_note(qtbot, window, saved_tab):
    path = saved_tab.reading_path
    qtbot.keyClicks(saved_tab.saved_reading.pane.note.editor, "Written before closing")
    window.close_tab(window.tab_widget.indexOf(saved_tab))

    reopened = window.open_saved_reading(path)

    assert reopened.saved_reading.pane.note.editor.toPlainText() == "Written before closing"


def test_of_two_notes_the_older_is_shown_and_edited(qtbot, window, saved_tab):
    path = saved_tab.reading_path
    window.close_tab(window.tab_widget.indexOf(saved_tab))
    older = path / "1700000000_first.md"
    newer = path / "1800000000.md"
    older.write_text("older", encoding="utf-8")
    newer.write_text("newer", encoding="utf-8")

    reopened = window.open_saved_reading(path)
    editor = reopened.saved_reading.pane.note.editor
    editor.moveCursor(editor.textCursor().MoveOperation.End)
    qtbot.keyClicks(editor, "!")
    reopened.flush_pending_edits()

    assert editor.toPlainText() == "older!"
    assert older.read_text(encoding="utf-8") == "older!"
    assert newer.read_text(encoding="utf-8") == "newer"


def test_a_note_that_is_not_utf8_is_passed_over_and_never_written_over(qtbot, window, saved_tab):
    path = saved_tab.reading_path
    window.close_tab(window.tab_widget.indexOf(saved_tab))
    latin = path / "1700000000.md"
    latin.write_bytes("caf\xe9".encode("latin-1"))
    # macOS leaves one beside each file it copies to a disk it can't tag
    (path / "._1700000000.md").write_bytes(b"\x00\x05\x16\x07\xff\xfe")

    reopened = window.open_saved_reading(path)
    editor = reopened.saved_reading.pane.note.editor
    assert editor.toPlainText() == ""
    qtbot.keyClicks(editor, "new")
    reopened.flush_pending_edits()

    assert latin.read_bytes() == "caf\xe9".encode("latin-1")
    written = [note for note in notes_in(path) if note != latin and not note.name.startswith("._")]
    assert [note.read_text(encoding="utf-8") for note in written] == ["new"]


def test_the_journal_lists_a_reading_whose_note_is_not_utf8(window, saved_tab):
    path = saved_tab.reading_path
    window.close_tab(window.tab_widget.indexOf(saved_tab))
    (path / "1700000000.md").write_bytes(b"\xff\xfe not utf-8")
    (path / "._1700000000.md").write_bytes(b"\x00\x05\x16\x07\xff")

    library = window.new_library_tab()
    page = library.readings_page
    page.refresh()

    assert page.list_model.rowCount() > 0


def test_save_as_reading_leaves_the_cursor_in_the_question(qtbot, focused):
    # The pane shows itself once the event loop runs, and takes focus then
    qtbot.waitUntil(focused.saved_reading.pane.question_edit.hasFocus)


def test_tab_from_the_question_lands_in_the_note(qtbot, focused):
    pane = focused.saved_reading.pane
    qtbot.waitUntil(pane.question_edit.hasFocus)

    qtbot.keyClick(pane.question_edit, Qt.Key.Key_Tab)

    assert pane.note.editor.hasFocus()
