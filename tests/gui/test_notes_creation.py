import pytest
from PyQt6.QtGui import QTextCursor

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.ui.tabs.card_view import notes_tab as notes_tab_module
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
from tests.conftest import MINIMAL_DECK_PATH


@pytest.fixture
def no_dialogs(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the creation path opened a dialog")

    monkeypatch.setattr(notes_tab_module.QInputDialog, "getText", staticmethod(refuse))


def open_card_view(qtbot, deck=None):
    deck = deck or TarotDeck(str(MINIMAL_DECK_PATH))
    card = next(c for c in deck.get_all_cards() if c.get("image"))
    tab = CardViewTab(card=card, deck=deck)
    qtbot.addWidget(tab)
    return tab, card


def test_new_opens_the_editor_without_asking_for_a_name(qtbot, notes_base, no_dialogs):
    tab, _ = open_card_view(qtbot)

    tab.notes_tab.create_new_note()

    assert tab.notes_tab.stack.currentIndex() == 2
    assert tab.notes_tab.pending_path is not None
    assert not notes_base.exists()


def test_the_file_appears_on_the_first_keystroke(qtbot, notes_base, no_dialogs):
    tab, card = open_card_view(qtbot)
    notes = tab.notes_tab

    notes.create_new_note()
    qtbot.keyClicks(notes.note_editor, "a line I came with")

    written = sorted((notes_base / card["id"]).glob("*.md"))
    assert len(written) == 1
    assert written[0].stem.isdigit()
    assert notes.pending_path is None
    assert notes.current_file_path == str(written[0])

    notes.save_current_note()
    assert written[0].read_text(encoding="utf-8") == "a line I came with"


def test_a_note_asked_for_and_abandoned_leaves_nothing_on_disk(qtbot, notes_base, no_dialogs):
    tab, _ = open_card_view(qtbot)

    tab.notes_tab.create_new_note()
    tab.notes_tab.show_note_list()

    assert not notes_base.exists()
    assert tab.notes_tab.pending_path is None


def test_opening_another_note_does_not_write_it_to_the_pending_path(qtbot, notes_base, no_dialogs):
    tab, card = open_card_view(qtbot)
    card_dir = notes_base / card["id"]
    card_dir.mkdir(parents=True)
    (card_dir / "1700000000_Existing.md").write_text("# Existing\n\nbody\n", encoding="utf-8")
    tab.notes_tab.load_card_notes(card)

    tab.notes_tab.create_new_note()
    tab.notes_tab.open_note_path(str(card_dir / "1700000000_Existing.md"))

    assert sorted(p.name for p in card_dir.iterdir()) == ["1700000000_Existing.md"]


def test_a_nameless_note_is_listed_by_its_first_line(qtbot, notes_base, no_dialogs):
    tab, _ = open_card_view(qtbot)
    notes = tab.notes_tab

    notes.create_new_note()
    qtbot.keyClicks(notes.note_editor, "a line I came with")

    listing = notes.notes_list_widget.notes_list
    assert listing.count() == 1
    assert listing.item(0).text() == "a line I came with"


def test_renaming_a_nameless_note_keeps_its_timestamp(qtbot, notes_base, monkeypatch):
    tab, card = open_card_view(qtbot)
    card_dir = notes_base / card["id"]
    card_dir.mkdir(parents=True)
    (card_dir / "1700000000.md").write_text("a line I came with\n", encoding="utf-8")
    tab.notes_tab.load_card_notes(card)

    listing = tab.notes_tab.notes_list_widget.notes_list
    listing.setCurrentItem(listing.item(0))
    monkeypatch.setattr(
        notes_tab_module.QInputDialog, "getText", staticmethod(lambda *a, **k: ("Lyrics", True))
    )

    tab.notes_tab.rename_current_note()

    assert sorted(p.name for p in card_dir.iterdir()) == ["1700000000_Lyrics.md"]


def test_a_nameless_note_is_not_offered_to_the_link_completer(qtbot, notes_base, no_dialogs):
    tab, card = open_card_view(qtbot)
    card_dir = notes_base / card["id"]
    card_dir.mkdir(parents=True)
    (card_dir / "1700000000.md").write_text("a line I came with\n", encoding="utf-8")
    (card_dir / "1700000001_Named.md").write_text("# Named\n\nbody\n", encoding="utf-8")
    tab.notes_tab.load_card_notes(card)

    suggestions = tab.notes_tab.get_link_suggestions()

    assert "Named" in suggestions
    assert "" not in suggestions


def test_an_empty_link_resolves_to_nothing(qtbot, notes_base, no_dialogs):
    tab, card = open_card_view(qtbot)
    card_dir = notes_base / card["id"]
    card_dir.mkdir(parents=True)
    (card_dir / "1700000000.md").write_text("a line I came with\n", encoding="utf-8")
    tab.notes_tab.load_card_notes(card)

    assert tab.notes_tab.find_note_by_title("") is None


def test_the_header_names_the_open_note(qtbot, notes_base, no_dialogs):
    tab, card = open_card_view(qtbot)
    card_dir = notes_base / card["id"]
    card_dir.mkdir(parents=True)
    (card_dir / "1700000000_Lyrics.md").write_text("# Lyrics\n\nbody\n", encoding="utf-8")
    tab.notes_tab.load_card_notes(card)

    tab.notes_tab.open_note_path(str(card_dir / "1700000000_Lyrics.md"))

    assert tab.notes_tab.note_title.text() == "Lyrics"


def test_the_header_shows_a_nameless_notes_name_as_empty_not_its_text(
    qtbot, notes_base, no_dialogs
):
    """The row is labelled by the note's first line."""
    tab, card = open_card_view(qtbot)
    card_dir = notes_base / card["id"]
    card_dir.mkdir(parents=True)
    (card_dir / "1700000000.md").write_text("a line I came with\n", encoding="utf-8")
    tab.notes_tab.load_card_notes(card)

    tab.notes_tab.open_note_path(str(card_dir / "1700000000.md"))

    assert tab.notes_tab.note_title.text() == ""


def test_typing_a_name_in_the_header_renames_the_file(qtbot, notes_base, no_dialogs):
    tab, card = open_card_view(qtbot)
    card_dir = notes_base / card["id"]
    card_dir.mkdir(parents=True)
    (card_dir / "1700000000.md").write_text("a line I came with\n", encoding="utf-8")
    tab.notes_tab.load_card_notes(card)
    tab.notes_tab.open_note_path(str(card_dir / "1700000000.md"))

    tab.notes_tab.note_title.setText("Lyrics")
    tab.notes_tab.note_title.editingFinished.emit()

    assert sorted(p.name for p in card_dir.iterdir()) == ["1700000000_Lyrics.md"]
    assert tab.notes_tab.current_file_path == str(card_dir / "1700000000_Lyrics.md")


def test_clearing_the_header_takes_the_name_back_off(qtbot, notes_base, no_dialogs):
    tab, card = open_card_view(qtbot)
    card_dir = notes_base / card["id"]
    card_dir.mkdir(parents=True)
    (card_dir / "1700000000_Lyrics.md").write_text("a line I came with\n", encoding="utf-8")
    tab.notes_tab.load_card_notes(card)
    tab.notes_tab.open_note_path(str(card_dir / "1700000000_Lyrics.md"))

    tab.notes_tab.note_title.setText("")
    tab.notes_tab.note_title.editingFinished.emit()

    assert sorted(p.name for p in card_dir.iterdir()) == ["1700000000.md"]


def test_a_name_typed_before_the_first_keystroke_lands_in_the_filename(
    qtbot, notes_base, no_dialogs
):
    tab, card = open_card_view(qtbot)
    notes = tab.notes_tab

    notes.create_new_note()
    notes.note_title.setText("Lyrics")
    notes.note_title.editingFinished.emit()
    qtbot.keyClicks(notes.note_editor, "a line I came with")

    written = sorted((notes_base / card["id"]).glob("*.md"))
    assert len(written) == 1
    assert written[0].name.endswith("_Lyrics.md")
    assert written[0].stem.split("_")[0].isdigit()


def test_naming_a_note_never_moves_its_id(qtbot, notes_base, no_dialogs):
    tab, card = open_card_view(qtbot)
    card_dir = notes_base / card["id"]
    card_dir.mkdir(parents=True)
    (card_dir / "1700000000.md").write_text("a line\n", encoding="utf-8")
    tab.notes_tab.load_card_notes(card)
    tab.notes_tab.open_note_path(str(card_dir / "1700000000.md"))

    for name in ("First", "Second", ""):
        tab.notes_tab.note_title.setText(name)
        tab.notes_tab.note_title.editingFinished.emit()

    assert [p.stem.split("_")[0] for p in card_dir.iterdir()] == ["1700000000"]


def type_into(qtbot, notes_tab, text):
    """Type at the end of the open note"""
    notes_tab.note_editor.moveCursor(QTextCursor.MoveOperation.End)
    qtbot.keyClicks(notes_tab.note_editor, text)


def open_with_a_note(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    card_dir = notes_base / card["id"]
    card_dir.mkdir(parents=True)
    path = card_dir / "1700000000_Lyrics.md"
    path.write_text("# Lyrics\n\noriginal\n", encoding="utf-8")
    tab.notes_tab.load_card_notes(card)
    tab.notes_tab.open_note_path(str(path))
    type_into(qtbot, tab.notes_tab, "edited")
    return tab, path


def test_raising_another_tab_of_the_same_card_saves(qtbot, notes_base, no_dialogs):
    tab, path = open_with_a_note(qtbot, notes_base)
    tab.show_notes_tab()

    tab.info_tabs.setCurrentWidget(tab.overview_tab)

    assert "edited" in path.read_text(encoding="utf-8")


def test_the_flush_hook_saves(qtbot, notes_base, no_dialogs):
    """What the main window calls on the tab it is leaving."""
    tab, path = open_with_a_note(qtbot, notes_base)

    tab.flush_pending_edits()

    assert "edited" in path.read_text(encoding="utf-8")


def test_switching_card_tabs_saves_the_one_being_left(qtbot, notes_base, no_dialogs):
    from tarot_canvas.ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    window.new_card_view_tab()
    first = window.tab_widget.currentWidget()
    card_dir = notes_base / first.card["id"]
    card_dir.mkdir(parents=True)
    path = card_dir / "1700000000_Lyrics.md"
    path.write_text("# Lyrics\n\noriginal\n", encoding="utf-8")
    first.notes_tab.load_card_notes(first.card)
    first.notes_tab.open_note_path(str(path))
    type_into(qtbot, first.notes_tab, "edited")

    window.new_card_view_tab()

    assert window.tab_widget.currentWidget() is not first
    assert "edited" in path.read_text(encoding="utf-8")


def test_a_tab_holding_nothing_unsaved_is_left_alone(qtbot, notes_base, no_dialogs):
    tab, _ = open_card_view(qtbot)

    assert tab.flush_pending_edits() is None
    assert tab.notes_tab.save_if_modified() is False
