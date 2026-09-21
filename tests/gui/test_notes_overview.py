"""The notes section on the card Overview.

The card's own notes, newest first and capped, or one static ghost row that is itself the
way to write the first one. It reads the Notes tab's index and never touches disk.
"""

import os
import time

import pytest

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.note_events import note_events
from tarot_canvas.ui.tabs.card_view import notes_text
from tarot_canvas.ui.tabs.card_view.notes_section import MAX_ROWS, GhostRow, NoteRow
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
from tests.conftest import MINIMAL_DECK_PATH


@pytest.fixture
def notes_base(tmp_path, monkeypatch):
    base = tmp_path / "notes"
    monkeypatch.setattr(notes_model, "notes_base", lambda: base)
    return base


def write_note(notes_base, card_id, filename, body):
    card_dir = notes_base / card_id
    card_dir.mkdir(parents=True, exist_ok=True)
    path = card_dir / filename
    path.write_text(body, encoding="utf-8")
    return path


def open_card_view(qtbot, register=True):
    deck = TarotDeck(str(MINIMAL_DECK_PATH))
    card = next(c for c in deck.get_all_cards() if c.get("image"))
    tab = CardViewTab(card=card, deck=deck)
    if register:
        qtbot.addWidget(tab)
    return tab, card


def rows(tab):
    section = tab.overview_tab.notes_section
    return [section.rows.itemAt(i).widget() for i in range(section.rows.count())]


def test_a_card_with_nothing_written_shows_one_ghost_row(qtbot, notes_base):
    tab, _ = open_card_view(qtbot)

    drawn = rows(tab)

    assert len(drawn) == 1
    assert isinstance(drawn[0], GhostRow)


def test_the_ghost_is_how_the_first_note_gets_written(qtbot, notes_base):
    tab, _ = open_card_view(qtbot)
    ghost = rows(tab)[0]

    ghost.clicked.emit()

    assert tab.info_tabs.currentWidget() is tab.notes_tab
    assert tab.notes_tab.pending_path is not None


def test_one_note_is_listed_with_its_opening_line(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(notes_base, card["id"], "1700000000_Lyrics.md", "# Lyrics\n\nthe longest night\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    drawn = rows(tab)

    assert len(drawn) == 1
    assert isinstance(drawn[0], NoteRow)
    assert drawn[0].title_label.full_text == "Lyrics"
    assert drawn[0].preview_label.full_text == "the longest night"


def test_a_stub_is_listed_but_shows_no_preview_line(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(notes_base, card["id"], "1700000000_Stub.md", "# Stub\n\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    row = rows(tab)[0]

    assert row.title_label.full_text == "Stub"
    assert row.preview_label.full_text == notes_text.text("stub_note")


def test_five_notes_are_capped_at_three_newest_first(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    for index in range(5):
        path = write_note(
            notes_base, card["id"], f"17000000{index:02d}_N{index}.md", f"# N{index}\n"
        )
        import os

        os.utime(path, (1700000000 + index, 1700000000 + index))
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    drawn = rows(tab)

    assert len(drawn) == MAX_ROWS
    assert [row.title_label.full_text for row in drawn] == ["N4", "N3", "N2"]


def test_a_nameless_note_is_listed_by_its_first_line(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(notes_base, card["id"], "1700000000.md", "a line I came with\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    assert rows(tab)[0].title_label.full_text == "a line I came with"


def test_a_nameless_note_never_shows_the_same_line_twice(qtbot, notes_base):
    """The bug from the .Devel build: label and preview were both line 0."""
    tab, card = open_card_view(qtbot)
    write_note(
        notes_base,
        card["id"],
        "1700000000.md",
        "what can you see on the horizon?\nand what lies beyond it\n",
    )
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    row = rows(tab)[0]

    assert row.title_label.full_text == "what can you see on the horizon?"
    assert row.preview_label.full_text == "and what lies beyond it"


def test_a_one_line_nameless_note_is_a_one_line_row(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(notes_base, card["id"], "1700000000.md", "the whole note\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    row = rows(tab)[0]

    assert row.title_label.full_text == "the whole note"
    assert row.preview_label.full_text == ""
    assert row.preview_label.isVisible() is False


def test_a_bare_opening_sentence_is_not_emphasised_like_a_title(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    write_note(notes_base, card["id"], "1700000000.md", "no name here\n")
    write_note(notes_base, card["id"], "1700000001_Named.md", "# Named\n\nbody\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    named = next(r for r in rows(tab) if r.title_label.full_text == "Named")
    nameless = next(r for r in rows(tab) if r.title_label.full_text == "no name here")

    assert named.title_label.font().bold() is True
    assert nameless.title_label.font().bold() is False


def test_a_heading_the_user_wrote_is_emphasised_even_with_no_filename_name(qtbot, notes_base):
    """`# Lyrics` in a nameless note is that line being declared a title."""
    tab, card = open_card_view(qtbot)
    write_note(
        notes_base,
        card["id"],
        "1700000000.md",
        '# Lyrics\n\n"Even the longest night must end"\n',
    )
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    row = rows(tab)[0]

    assert row.title_label.full_text == "Lyrics"
    assert row.title_label.font().bold() is True
    assert row.preview_label.full_text == '"Even the longest night must end"'


def test_clicking_a_row_raises_the_notes_tab_with_that_note_open(qtbot, notes_base):
    tab, card = open_card_view(qtbot)
    path = write_note(notes_base, card["id"], "1700000000_Lyrics.md", "# Lyrics\n\nbody\n")
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    rows(tab)[0].clicked.emit()

    assert tab.info_tabs.currentWidget() is tab.notes_tab
    assert tab.notes_tab.current_file_path == str(path)
    assert tab.notes_tab.stack.currentIndex() == 2


def test_writing_a_note_replaces_the_ghost_without_reloading_the_card(qtbot, notes_base):
    tab, _ = open_card_view(qtbot)
    assert isinstance(rows(tab)[0], GhostRow)

    tab.notes_tab.create_new_note()
    qtbot.keyClicks(tab.notes_tab.note_editor, "a line I came with")

    # The ghost is gone the moment the note has a file, without the card reloading
    assert isinstance(rows(tab)[0], NoteRow)

    # The section lists what is written, so it follows the editor's saves, not its
    # keystrokes: the Notes tab owns the unsaved buffer and this is only a reader.
    tab.notes_tab.save_current_note()
    assert rows(tab)[0].title_label.full_text == "a line I came with"


def test_the_section_stops_listening_when_its_card_view_is_gone(qtbot, notes_base):
    # Deleted by hand rather than at teardown, which is the case under test
    tab, _ = open_card_view(qtbot, register=False)

    tab.deleteLater()
    qtbot.wait(10)

    # A slot left on the singleton would raise on the next write from anywhere
    note_events().notes_changed.emit()


def test_the_section_is_headed_by_the_name_adam_gave_it(qtbot, notes_base):
    tab, _ = open_card_view(qtbot)

    heading = tab.overview_tab.notes_section.heading

    assert heading.text() == "Personal Notes"
    assert heading.isVisibleTo(tab.overview_tab)


def test_the_description_heading_is_not_punctuated_as_a_form_label(qtbot, notes_base):
    """A colon marks a label in front of a control; this heads a block of prose."""
    tab, _ = open_card_view(qtbot)

    assert tab.overview_tab.description_header.text() == "Description"


def test_the_overview_headings_share_one_size(qtbot, notes_base):
    """Description and Personal Notes are peers, and both sit under the card's name."""
    tab, _ = open_card_view(qtbot)
    overview = tab.overview_tab

    section = overview.notes_section.heading.font().pointSizeF()
    assert overview.description_header.font().pointSizeF() == pytest.approx(section)
    assert overview.name_label.font().pointSizeF() > section


def test_a_rows_date_uses_the_wording_the_about_dialog_already_had(qtbot, notes_base):
    """One ladder, shared: the section invents no phrasing of its own."""
    tab, card = open_card_view(qtbot)
    path = write_note(notes_base, card["id"], "1700000000_Lyrics.md", "# Lyrics\n\nbody\n")
    os.utime(path, (time.time(), time.time()))
    tab.notes_tab.load_card_notes(card)
    tab.overview_tab.refresh_notes()

    row = rows(tab)[0]

    assert row.date_label.full_text == "Today"
    assert row.date_label.isVisibleTo(row) is True
