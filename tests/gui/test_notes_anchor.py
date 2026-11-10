"""The Notes tab works on any directory, not only a card's: a card is one caller of it."""

import os

import pytest
from PyQt6.QtWidgets import QInputDialog

from tarot_canvas.models.notes import NoteAnchor
from tarot_canvas.ui.tabs.card_view.notes_tab import NotesTab


@pytest.fixture
def no_dialogs(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a dialog opened")

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(refuse))


@pytest.fixture
def folder(tmp_path):
    return tmp_path / "elsewhere"


@pytest.fixture
def notes(qtbot, notes_base, folder, no_dialogs):
    tab = NotesTab()
    qtbot.addWidget(tab)
    tab.set_anchor(NoteAnchor(folder))
    return tab


def names(directory):
    return sorted(path.name for path in directory.iterdir())


def test_a_new_note_is_written_into_the_anchor_folder(qtbot, notes, notes_base, folder):
    notes.create_new_note()
    qtbot.keyClicks(notes.note_editor, "a line I came with")

    written = sorted(folder.glob("*.md"))
    assert len(written) == 1
    assert written[0].stem.isdigit()
    assert not notes_base.exists()

    notes.show_note_list()
    assert notes.list_model.rowCount() == 1
    assert notes.list_model.index(0, 0).data() == "a line I came with"


def test_renaming_keeps_the_timestamp(qtbot, notes, folder):
    folder.mkdir()
    (folder / "1700000000.md").write_text("a line I came with\n", encoding="utf-8")
    notes.refresh_list()

    notes.list_model.setData(notes.list_model.index(0, 0), "Lyrics")

    qtbot.waitUntil(lambda: names(folder) == ["1700000000_Lyrics.md"])


def test_delete_then_undo_restores_the_note(notes, folder):
    folder.mkdir()
    path = folder / "1700000000_Kept.md"
    path.write_text("# Kept\n\nbody\n", encoding="utf-8")
    notes.refresh_list()

    notes.delete_note(str(path))
    assert not path.exists()
    assert notes.list_model.rowCount() == 0

    notes.undo_action.trigger()
    assert path.read_text(encoding="utf-8") == "# Kept\n\nbody\n"
    assert notes.list_model.rowCount() == 1


def test_a_link_resolves_to_the_newest_card_note_with_that_title(notes, notes_base):
    paths = []
    for card_id, stamp in (
        ("major_arcana.fool", 1700000000),
        ("major_arcana.magician", 1700000100),
    ):
        path = notes_base / card_id / f"{stamp}_Shared.md"
        path.parent.mkdir(parents=True)
        path.write_text("# Shared\n\nbody\n", encoding="utf-8")
        os.utime(path, (stamp, stamp))
        paths.append(path)
    _older, newer = paths
    notes.refresh_list()

    assert notes.find_note_by_title("Shared").path == newer
