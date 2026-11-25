"""A leading > finds the window's and the current tab's commands, and Enter runs one"""

import pytest
from PyQt6.QtCore import Qt

from tarot_canvas.ui import command_palette, commands
from tarot_canvas.ui.card_view.notes_tab import NotesTab
from tarot_canvas.ui.command_palette import ROW_ROLE, CommandPalette
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.style.theme_manager import ThemeType
from tests.gui.test_main_window import activate, make_shown_window


@pytest.fixture(autouse=True)
def no_recent_commands(monkeypatch):
    monkeypatch.setattr(command_palette, "_RECENT", [])


class Opened:
    """What the palette showed for a search, and whether its hint was up"""

    def __init__(self, palette):
        self.rows = [
            palette.results_list.item(row).data(ROW_ROLE) for row in palette.visible_rows()
        ]
        self.titles = [row.title for row in self.rows]
        self.hint = palette.hint_label.isVisibleTo(palette)


def search(qtbot, monkeypatch, window, *texts, enter=False):
    """Open the palette, type each text in turn, and press Enter after the last if asked"""
    seen = []

    def exec_(palette):
        palette.show()
        qtbot.waitExposed(palette)
        for text in texts:
            palette.search_input.setText(text)
            seen.append(Opened(palette))
        if enter:
            qtbot.keyClick(palette.search_input, Qt.Key.Key_Return)
        palette.close()

    monkeypatch.setattr(CommandPalette, "exec", exec_)
    window.show_command_palette()
    return seen[-1] if len(seen) == 1 else seen


def canvas_window(qtbot, deck=None):
    window = make_shown_window(qtbot)
    canvas = window.new_canvas_tab()
    if deck is not None:
        canvas.add_specific_card(deck.cards[0], card_deck=deck)
    activate(qtbot, window, canvas.view)
    return window, canvas


def test_zoom_on_a_canvas_lists_the_three_zooms_with_their_keys_and_enter_zooms_in(
    qtbot, monkeypatch
):
    window, canvas = canvas_window(qtbot)
    scale = canvas.view.transform().m11()

    opened = search(qtbot, monkeypatch, window, ">zoom", enter=True)

    assert opened.titles == ["Zoom In", "Zoom Out", "Reset Zoom"]
    assert [row.trailing for row in opened.rows] == [
        ("View", commands.key_text(command_id))
        for command_id in ("window.zoom_in", "window.zoom_out", "window.reset_zoom")
    ]
    assert canvas.view.transform().m11() > scale


def test_flip_is_found_on_a_canvas_and_not_in_a_card_view(qtbot, monkeypatch, minimal_deck):
    window, canvas = canvas_window(qtbot, minimal_deck)
    canvas.scene.items()[0].setSelected(True)
    assert search(qtbot, monkeypatch, window, ">flip").titles == [
        commands.by_id("canvas.flip").text
    ]

    window.open_card_view_tab(minimal_deck.cards[0], minimal_deck)
    assert search(qtbot, monkeypatch, window, ">flip").titles == []


def test_new_note_is_found_in_a_card_view_and_enter_starts_one(qtbot, monkeypatch, minimal_deck):
    window = make_shown_window(qtbot)
    tab = window.open_card_view_tab(minimal_deck.cards[0], minimal_deck)
    notes = tab.findChild(NotesTab)
    assert notes.pending_path is None

    opened = search(qtbot, monkeypatch, window, ">new note", enter=True)

    assert opened.titles == [commands.by_id("notes.new_note").text]
    assert opened.rows[0].trailing[0] == "Notes"
    assert notes.pending_path is not None


def test_a_disabled_command_is_not_listed(qtbot, monkeypatch, clipboard):
    window, _canvas = canvas_window(qtbot)

    assert search(qtbot, monkeypatch, window, ">paste").titles == []


def test_a_theme_runs_from_the_palette_and_shows_checked_on_the_next_open(qtbot, monkeypatch):
    chosen = []
    monkeypatch.setattr(MainWindow, "change_theme", lambda self, theme: chosen.append(theme))
    window = make_shown_window(qtbot)
    assert not search(qtbot, monkeypatch, window, ">dark").rows[0].checked

    search(qtbot, monkeypatch, window, ">dark", enter=True)

    assert chosen == [ThemeType.DARK]
    (dark,) = search(qtbot, monkeypatch, window, ">dark").rows
    assert dark.checked
    assert dark.radio


def test_a_bare_greater_than_lists_the_last_command_run_first(qtbot, monkeypatch):
    window, _canvas = canvas_window(qtbot)
    first = search(qtbot, monkeypatch, window, ">").titles[0]
    assert first != "Reset Zoom"

    search(qtbot, monkeypatch, window, ">reset zoom", enter=True)

    assert search(qtbot, monkeypatch, window, ">").titles[:2] == ["Reset Zoom", first]


def test_typing_greater_than_hides_the_hint_and_deleting_it_brings_the_cards_back(
    qtbot, monkeypatch, minimal_deck
):
    window = make_shown_window(qtbot)

    cards, commanding, back = search(qtbot, monkeypatch, window, "", ">", "")

    assert cards.hint and back.hint
    assert not commanding.hint
    assert cards.titles == back.titles == [card.display_name for card in minimal_deck.cards]
    assert commanding.titles
    assert not set(commanding.titles) & set(cards.titles)


def test_the_palette_does_not_list_itself(qtbot, monkeypatch):
    window = make_shown_window(qtbot)

    assert search(qtbot, monkeypatch, window, ">find card").titles == []
