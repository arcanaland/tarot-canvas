"""The Library's second view: the sidebar, the list and the pane."""

import os

import pytest
from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtGui import QFontDatabase, QPalette
from PyQt6.QtWidgets import QFrame, QTabBar

from tarot_canvas.models import notes as notes_model
from tarot_canvas.models.note_events import note_events
from tarot_canvas.settings import (
    LIBRARY_VIEW_DECKS,
    LIBRARY_VIEW_KEY,
    LIBRARY_VIEW_NOTES,
    LIBRARY_VIEWS,
    get_settings,
)
from tarot_canvas.ui.library import notes_text as notes_text_module
from tarot_canvas.ui.library.deck_model import SubtitleRole
from tarot_canvas.ui.library.notes_model import CardIdRole, PreviewRole
from tarot_canvas.ui.tabs.library_tab import LibraryTab

FOOL = "major_arcana.00"
MAGICIAN = "major_arcana.01"


@pytest.fixture
def notes_base(tmp_path, monkeypatch):
    base = tmp_path / "notes"
    monkeypatch.setattr(notes_model, "notes_base", lambda: base)
    return base


def write_note(base, card_id, title="A Note", body="a line of prose\n"):
    card_dir = base / card_id
    card_dir.mkdir(parents=True, exist_ok=True)
    path = card_dir / f"1700000000_{title.replace(' ', '_')}.md"
    path.write_text(f"# {title}\n\n{body}", encoding="utf-8")
    return path


@pytest.fixture
def library(qtbot, notes_base):
    tab = LibraryTab()
    qtbot.addWidget(tab)
    return tab


def notes_view(tab):
    tab.show_view(LIBRARY_VIEW_NOTES)
    return tab.notes_page


def select(page, card_id):
    view = page.list_view
    model = view.model()
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        if index.data(CardIdRole) == card_id:
            view.selectionModel().setCurrentIndex(
                index, QItemSelectionModel.SelectionFlag.ClearAndSelect
            )
            return index
    raise AssertionError(f"no row for {card_id}")


# -- the sidebar ---------------------------------------------------------


def sidebar_views(library):
    return [
        library.sidebar.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(library.sidebar.count())
    ]


def test_the_sidebar_lists_the_views_in_order(library):
    assert sidebar_views(library) == list(LIBRARY_VIEWS)
    assert library.current_view() == LIBRARY_VIEW_DECKS
    assert library.sidebar.currentRow() == 0


def test_the_header_has_no_tab_bar(library):
    assert library.findChildren(QTabBar) == []


def test_selecting_a_row_switches_the_page_and_the_pane(library):
    library.sidebar.setCurrentRow(LIBRARY_VIEWS.index(LIBRARY_VIEW_NOTES))

    assert library.current_view() == LIBRARY_VIEW_NOTES
    assert library.pages.currentWidget() is library.notes_page
    assert library.current_details_pane() is library.notes_page.details_pane


def test_show_view_selects_the_row(library):
    library.show_view(LIBRARY_VIEW_NOTES)

    assert library.sidebar.currentItem().data(Qt.ItemDataRole.UserRole) == LIBRARY_VIEW_NOTES
    assert library.sidebar.currentItem().isSelected()


def test_the_sidebar_never_leaves_no_view_selected(library):
    library.show_view(LIBRARY_VIEW_NOTES)

    library.sidebar.clearSelection()

    assert [item.data(Qt.ItemDataRole.UserRole) for item in library.sidebar.selectedItems()] == [
        LIBRARY_VIEW_NOTES
    ]
    assert library.current_view() == LIBRARY_VIEW_NOTES


def test_up_and_down_switch_views(library, qtbot):
    library.show()
    qtbot.waitExposed(library)
    library.sidebar.setFocus()

    qtbot.keyClick(library.sidebar, Qt.Key.Key_Down)
    assert library.current_view() == LIBRARY_VIEW_NOTES

    qtbot.keyClick(library.sidebar, Qt.Key.Key_Up)
    assert library.current_view() == LIBRARY_VIEW_DECKS


def test_the_sidebar_comes_before_the_search_field_in_the_tab_order(library):
    widget = library.sidebar.nextInFocusChain()
    while not widget.focusPolicy() & Qt.FocusPolicy.TabFocus:
        widget = widget.nextInFocusChain()

    assert widget is library.search_field


def test_the_sidebar_is_drawn_on_the_window_colour(library, qtbot):
    """As Dolphin's Places panel is: chrome, not content."""
    library.resize(800, 500)
    library.show()
    qtbot.waitExposed(library)

    image = library.grab().toImage()
    sidebar = library.sidebar.geometry()
    below_rows = sidebar.bottom() - 5

    assert not library.sidebar.viewport().autoFillBackground()
    assert image.pixelColor(sidebar.center().x(), below_rows) == library.palette().color(
        QPalette.ColorRole.Window
    )


def test_the_seam_beside_the_sidebar_starts_below_the_header(library, qtbot):
    library.show()
    qtbot.waitExposed(library)

    header_bottom = library.header.mapTo(library, library.header.rect().bottomLeft()).y()
    seams = [
        frame
        for frame in library.findChildren(QFrame)
        if frame.frameShape() == QFrame.Shape.VLine
        and frame.mapTo(library, frame.rect().topLeft()).x() <= library.sidebar.width() + 1
    ]

    assert seams
    assert all(frame.mapTo(library, frame.rect().topLeft()).y() > header_bottom for frame in seams)


def test_the_first_sidebar_row_is_level_with_the_search_field(library, qtbot):
    library.show()
    qtbot.waitExposed(library)

    viewport = library.sidebar.viewport()
    row = library.sidebar.visualItemRect(library.sidebar.item(0))
    row_centre = viewport.mapTo(library, row.center()).y()
    field = library.search_field
    field_centre = field.mapTo(library, field.rect().center()).y()

    assert abs(row_centre - field_centre) <= 1


def test_the_sidebar_rows_are_named_and_have_icons(library):
    names = [library.sidebar.item(row).text() for row in range(library.sidebar.count())]

    assert names == ["Decks", notes_text_module.text("view_name")]
    assert all(names)


def test_switching_shows_the_notes_page_and_its_pane(library):
    page = notes_view(library)

    assert library.pages.currentWidget() is page
    assert library.current_details_pane() is page.details_pane


def test_the_chosen_view_is_remembered(library, qtbot, notes_base):
    notes_view(library)
    assert get_settings().value(LIBRARY_VIEW_KEY, type=str) == LIBRARY_VIEW_NOTES

    reopened = LibraryTab()
    qtbot.addWidget(reopened)
    assert reopened.current_view() == LIBRARY_VIEW_NOTES


def test_sort_size_and_open_deck_are_the_deck_views_alone(library, qtbot):
    library.show()
    qtbot.waitExposed(library)
    assert library.sort_combo.isVisible()
    assert library.open_deck_button.isVisible()

    assert library.density_combo.isVisible()

    notes_view(library)

    assert not library.sort_combo.isVisible()
    assert not library.open_deck_button.isVisible()
    # The list has no covers to size; search serves both
    assert not library.density_combo.isVisible()
    assert library.search_field.isVisible()


def test_switching_views_clears_a_search_meant_for_the_other(library, notes_base):
    library.search_field.setText("zodiac")
    notes_view(library)

    assert library.search_field.text() == ""
    assert library.notes_page.list_model.search() == ""


# -- the list ------------------------------------------------------------


def test_the_list_is_one_row_per_note(library, notes_base):
    write_note(notes_base, FOOL, title="First")
    write_note(notes_base, FOOL, title="Second")
    write_note(notes_base, MAGICIAN, title="Third")
    page = notes_view(library)
    page.refresh()

    assert page.list_model.rowCount() == 3


def test_search_in_this_view_leaves_the_deck_grid_alone(library, notes_base):
    write_note(notes_base, FOOL, title="Beginnings")
    write_note(notes_base, MAGICIAN, title="Tools")
    page = notes_view(library)
    page.refresh()

    library.search_field.setText("beginn")

    assert [
        page.list_model.index(row, 0).data(CardIdRole) for row in range(page.list_model.rowCount())
    ] == [FOOL]
    assert library.proxy_model.filterRegularExpression().pattern() == ""


def test_a_body_search_shows_the_matching_line_as_the_preview(library, notes_base):
    write_note(notes_base, FOOL, title="Untitled", body="the opening\na leap into thin air\n")
    page = notes_view(library)
    page.refresh()
    assert page.list_model.index(0, 0).data(PreviewRole) == "the opening"

    library.search_field.setText("thin air")

    assert page.list_model.rowCount() == 1
    assert page.list_model.index(0, 0).data(PreviewRole) == "a leap into thin air"


def test_select_card_selects_its_newest_note(library, notes_base):
    old = write_note(notes_base, FOOL, title="Old")
    new = write_note(notes_base, FOOL, title="New")
    os.utime(old, (1_700_000_000, 1_700_000_000))
    os.utime(new, (1_800_000_000, 1_800_000_000))
    page = notes_view(library)
    page.refresh()

    assert page.select_card(FOOL)
    assert page.list_view.currentIndex().data(Qt.ItemDataRole.DisplayRole) == "New"


# -- the pane ------------------------------------------------------------


def test_selecting_a_card_fills_the_pane_and_enables_the_toggle(library, notes_base):
    write_note(notes_base, FOOL, title="Beginnings")
    page = notes_view(library)
    page.refresh()

    select(page, FOOL)
    details = page.details_pane.details()

    assert details.card_id == FOOL
    assert [note.title for note in details.notes] == ["Beginnings"]
    assert library.details_toggle.isEnabled()


def test_the_pane_shows_the_first_line_of_each_note(library, notes_base):
    write_note(notes_base, FOOL, title="Beginnings", body="a leap into thin air\n")
    page = notes_view(library)
    page.refresh()

    select(page, FOOL)
    blocks = page.details_pane.note_widgets()

    assert len(blocks) == 1
    assert blocks[0].body_label.text() == "a leap into thin air"


def test_a_note_row_shows_its_card_in_the_pane(library, notes_base):
    """The pane is per-card: a row names the card, not itself."""
    write_note(notes_base, FOOL, title="Beginnings")
    page = notes_view(library)
    page.refresh()

    select(page, FOOL)
    details = page.details_pane.details()

    assert details.card_id == FOOL
    assert details.name == "The Fool"
    assert details.cover_path
    assert [note.title for note in details.notes] == ["Beginnings"]


def test_a_card_the_search_hides_still_fills_the_pane(library, notes_base):
    """The pane reads the index, not a row, so filtering never empties it."""
    write_note(notes_base, FOOL, title="Beginnings")
    page = notes_view(library)
    page.refresh()
    select(page, FOOL)

    page.set_search("nothing matches this")
    page._show_card(FOOL)

    assert page.details_pane.details().name == "The Fool"


def test_the_pane_writes_nothing(library, notes_base):
    """Every write goes through the card view's Notes tab; this pane only reads."""
    page = notes_view(library)

    assert not hasattr(page.details_pane, "create_note")
    assert not hasattr(page.details_pane, "delete_note")


# -- staying current -----------------------------------------------------


def test_a_note_written_elsewhere_reaches_the_list(library, notes_base):
    page = notes_view(library)
    assert page.list_model.rowCount() == 0

    write_note(notes_base, FOOL)
    note_events().notes_changed.emit()

    assert page.list_model.rowCount() == 1


def test_a_write_keeps_the_selection_and_refreshes_the_pane(library, notes_base):
    write_note(notes_base, FOOL, title="Draft")
    page = notes_view(library)
    page.refresh()
    select(page, FOOL)

    write_note(notes_base, FOOL, title="Beginnings")
    note_events().notes_changed.emit()

    assert page.details_pane.details().card_id == FOOL
    assert sorted(note.title for note in page.details_pane.details().notes) == [
        "Beginnings",
        "Draft",
    ]
    assert page.list_view.currentIndex().data(CardIdRole) == FOOL


# -- words ---------------------------------------------------------------


@pytest.fixture
def unwritten_strings(monkeypatch):
    for key in ("empty_no_match", "open_card", "search_placeholder"):
        monkeypatch.setitem(notes_text_module.NOTES_TEXT, key, "")


def test_an_unwritten_string_hides_the_element_it_labels(unwritten_strings, library, notes_base):
    """Every string in this view is Adam's; until he writes one, nothing speaks for him."""
    page = notes_view(library)
    page.set_search("nothing matches this")

    assert notes_text_module.text("empty_no_match") == ""
    assert page.empty_label.isHidden()
    assert page.details_pane.open_button.isHidden()
    assert library.search_field.placeholderText() == ""


def test_a_written_string_shows_its_element(library, notes_base, monkeypatch):
    monkeypatch.setitem(notes_text_module.NOTES_TEXT, "open_card", "Open card")
    write_note(notes_base, FOOL)
    page = notes_view(library)
    page.refresh()

    select(page, FOOL)

    assert not page.details_pane.open_button.isHidden()
    assert page.details_pane.open_button.text() == "Open card"


def test_the_card_id_is_bare_and_in_the_system_fixed_width_font(library, notes_base):
    write_note(notes_base, FOOL)
    page = notes_view(library)
    page.refresh()

    select(page, FOOL)

    label = page.details_pane.card_id_label
    fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    assert label.text() == FOOL
    assert label.font().family() == fixed.family()


def test_the_notes_view_uses_no_stylesheet_of_its_own(library):
    page = notes_view(library)

    assert library.sidebar.styleSheet() == ""
    assert page.list_view.styleSheet() == ""
    assert page.details_pane.styleSheet() == ""


def test_a_row_is_activated_by_its_card_id(library, notes_base, qtbot):
    write_note(notes_base, FOOL)
    page = notes_view(library)
    page.refresh()
    index = select(page, FOOL)

    with qtbot.waitSignal(page.card_activated) as caught:
        page.list_view.activated.emit(index)

    assert caught.args == [FOOL]


def test_a_row_names_its_card_in_the_subtitle(library, notes_base):
    write_note(notes_base, FOOL, title="Beginnings")
    page = notes_view(library)
    page.refresh()

    row = select(page, FOOL)
    assert row.data(Qt.ItemDataRole.DisplayRole) == "Beginnings"
    assert "The Fool" in row.data(SubtitleRole)
