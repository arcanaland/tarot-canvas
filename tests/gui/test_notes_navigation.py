"""From a row in the notes list to the note itself, and back to one Library."""

import pytest

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.note_events import note_events
from tarot_canvas.settings import LIBRARY_VIEW_NOTES
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.card_view_tab import CardViewTab
from tarot_canvas.ui.tabs.library_tab import LibraryTab

FOOL = "major_arcana.00"
MAGICIAN = "major_arcana.01"


@pytest.fixture
def notes_base(tmp_path, monkeypatch):
    base = tmp_path / "notes"
    monkeypatch.setattr(notes_model, "notes_base", lambda: base)
    return base


@pytest.fixture
def window(qtbot, notes_base):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def card_tabs(window):
    return [
        window.tab_widget.widget(index)
        for index in range(window.tab_widget.count())
        if isinstance(window.tab_widget.widget(index), CardViewTab)
    ]


# -- one Library ---------------------------------------------------------


def test_a_second_library_request_raises_the_first(window):
    first = window.new_library_tab()
    window.new_canvas_tab()

    second = window.new_library_tab()

    assert second is first
    assert window.tab_widget.currentWidget() is first
    assert len([t for t in _tabs(window) if isinstance(t, LibraryTab)]) == 1


def test_a_library_can_be_asked_for_a_particular_view(window):
    library = window.new_library_tab(view=LIBRARY_VIEW_NOTES)

    assert library.current_view() == LIBRARY_VIEW_NOTES


def _tabs(window):
    return [window.tab_widget.widget(index) for index in range(window.tab_widget.count())]


# -- a row opens its card ----------------------------------------------


def test_activating_a_row_opens_the_card_view_on_its_notes(window):
    library = window.new_library_tab(view=LIBRARY_VIEW_NOTES)

    library.on_card_activated(FOOL)

    opened = card_tabs(window)
    assert len(opened) == 1
    assert opened[0].card["id"] == FOOL
    assert opened[0].info_tabs.currentWidget() is opened[0].notes_tab


def test_a_second_activation_raises_the_same_card_tab(window):
    library = window.new_library_tab(view=LIBRARY_VIEW_NOTES)
    library.on_card_activated(FOOL)
    window.tab_widget.setCurrentWidget(library)

    library.on_card_activated(FOOL)

    assert len(card_tabs(window)) == 1
    assert window.tab_widget.currentWidget() is card_tabs(window)[0]
    assert card_tabs(window)[0].info_tabs.currentWidget() is card_tabs(window)[0].notes_tab


def test_a_card_the_reference_deck_lacks_opens_nothing(window):
    library = window.new_library_tab(view=LIBRARY_VIEW_NOTES)

    library.on_card_activated("minor_arcana.pentacles.king")

    assert card_tabs(window) == []


def test_a_card_view_opened_any_other_way_starts_on_overview(window, minimal_deck):
    window.open_card_view_tab(minimal_deck.get_card_by_id(FOOL), minimal_deck)

    opened = card_tabs(window)[0]
    assert opened.info_tabs.currentWidget() is opened.overview_tab


# -- a write reaches the library ----------------------------------------


def test_writing_a_note_in_a_card_tab_reaches_the_library(window, qtbot, notes_base, minimal_deck):
    library = window.new_library_tab(view=LIBRARY_VIEW_NOTES)
    window.open_card_view_tab(minimal_deck.get_card_by_id(FOOL), minimal_deck, show_notes=True)
    notes_tab = card_tabs(window)[0].notes_tab

    path = notes_base / FOOL / "1700000000_Written.md"
    path.parent.mkdir(parents=True)
    notes_tab.note_editor.setPlainText("# Written\n\na line\n")
    with qtbot.waitSignal(note_events().notes_changed):
        notes_tab.save_note_to_file(str(path))

    assert library.notes_page.list_model.rowCount() == 1


def test_an_autosave_over_an_untouched_note_says_nothing(window, notes_base, minimal_deck):
    """Otherwise the list rebuilds every thirty seconds for the life of the app."""
    window.open_card_view_tab(minimal_deck.get_card_by_id(FOOL), minimal_deck)
    notes_tab = card_tabs(window)[0].notes_tab

    path = notes_base / FOOL / "1700000000_Written.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Written\n\na line\n", encoding="utf-8")
    notes_tab.current_file_path = str(path)
    notes_tab.note_editor.document().setModified(False)

    heard = []
    note_events().notes_changed.connect(lambda: heard.append(True))
    notes_tab.auto_save()

    assert heard == []
