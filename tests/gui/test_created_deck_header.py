"""A created deck's header: Add images…, its fields edited in place, and the Cards choice"""

import os
import tomllib

import pytest
import tomlkit
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QLabel, QRadioButton, QToolButton

from tarot_canvas.models import deck_writer as writer
from tarot_canvas.ui.deck_view import deck_editor
from tarot_canvas.ui.strings import DECK_VIEW
from tarot_canvas.ui.widgets.inline_editors import InlineLineEdit, InlineTextEdit
from tests.conftest import MINIMAL_DECK_PATH
from tests.gui.test_created_deck_view import image_of, picture, settled, shown, unsorted_files

FOOL = "major_arcana.00"
MAGICIAN = "major_arcana.01"
PRIESTESS = "major_arcana.02"
EMPRESS = "major_arcana.03"
TWO_OF_CUPS = "minor_arcana.cups.two"


@pytest.fixture
def created(tmp_path, curation_file):
    return writer.create("Created", decks_root=tmp_path / "decks")


@pytest.fixture
def tab(qtbot, created):
    return settled(qtbot, shown(qtbot, created))


@pytest.fixture
def active(qtbot, created):
    """The tab, active, so focus moves as it would on screen"""
    tab = shown(qtbot, created)
    with qtbot.waitActive(tab):
        tab.activateWindow()
    return settled(qtbot, tab)


@pytest.fixture
def chosen(monkeypatch):
    """The files Add images… returns next"""
    picked = []
    monkeypatch.setattr(
        deck_editor.QFileDialog,
        "getOpenFileNames",
        lambda *args: ([os.fspath(path) for path in picked], ""),
    )
    return picked


@pytest.fixture
def warnings(monkeypatch):
    shown_ = []
    monkeypatch.setattr(deck_editor.QMessageBox, "warning", lambda *args: shown_.append(args[2]))
    return shown_


def tall(folder, name, height):
    image = QImage(10, height, QImage.Format.Format_RGB32)
    image.fill(QColor("blue"))
    path = folder / name
    assert image.save(os.fspath(path))
    return path


def manifest(deck):
    with open(deck / "deck.toml", "rb") as handle:
        return tomllib.load(handle)


def reloads(tab, monkeypatch):
    """How many times the tab shows a reloaded deck"""
    count = []
    original = tab.set_deck
    monkeypatch.setattr(tab, "set_deck", lambda deck: (count.append(deck), original(deck)))
    return count


# -- Add images… ----------------------------------------------------------------------------


def test_add_images_places_what_it_recognises_and_the_rest_go_to_unsorted(
    qtbot, tab, tmp_path, created, chosen, monkeypatch
):
    folder = tmp_path / "scans"
    folder.mkdir()
    for name in ("01.png", "02.png", "03.png", "00.png", "fool.png", "IMG_2041.png"):
        chosen.append(picture(folder, name))
    shown_decks = reloads(tab, monkeypatch)

    tab.header.add_images_button.click()
    settled(qtbot, tab)

    assert all(image_of(tab, card) for card in (MAGICIAN, PRIESTESS, EMPRESS))
    assert not image_of(tab, FOOL)
    assert unsorted_files(created) == ["00.png", "IMG_2041.png", "fool.png"]
    assert len(shown_decks) == 1


def test_add_images_never_replaces_a_filled_slot(qtbot, tab, tmp_path, created, chosen):
    tab.editor.queue.place(FOOL, picture(tmp_path, "first.png"))
    settled(qtbot, tab)
    chosen.append(picture(tmp_path, "00.png", "green"))

    tab.header.add_images_button.click()
    settled(qtbot, tab)

    assert os.path.basename(image_of(tab, FOOL)) == "00.png"
    assert (created / writer.SOURCE / "major_arcana" / "00" / "first.png").is_file()
    assert unsorted_files(created) == ["00.png"]


def test_add_images_of_two_heights_gives_one_root_at_the_shorter(
    qtbot, tab, tmp_path, created, chosen
):
    chosen.extend([tall(tmp_path, "00.png", 4800), tall(tmp_path, "01.png", 2000)])

    tab.header.add_images_button.click()
    settled(qtbot, tab)

    assert sorted(entry.name for entry in created.iterdir() if entry.name.startswith("h")) == [
        "h2000"
    ]
    assert image_of(tab, FOOL) and image_of(tab, MAGICIAN)


def test_files_that_fail_are_reported_once_and_the_rest_land(
    qtbot, tab, tmp_path, chosen, warnings
):
    for name in ("02.png", "03.png"):
        broken = tmp_path / name
        broken.write_text("not an image")
        chosen.append(broken)
    chosen.append(picture(tmp_path, "00.png"))

    tab.header.add_images_button.click()
    settled(qtbot, tab)

    assert image_of(tab, FOOL)
    assert warnings == [DECK_VIEW["add_images_failed"].format(count=2, files="02.png\n03.png")]


def test_several_files_dropped_on_unsorted_are_recognised(qtbot, tab, tmp_path, created):
    files = [picture(tmp_path, "00.png"), picture(tmp_path, "IMG_1.png")]

    tab.editor.unsorted.files_dropped.emit([os.fspath(path) for path in files])
    settled(qtbot, tab)

    assert image_of(tab, FOOL)
    assert unsorted_files(created) == ["IMG_1.png"]


def test_one_file_dropped_on_unsorted_stays_there(qtbot, tab, tmp_path, created):
    tab.editor.unsorted.files_dropped.emit([os.fspath(picture(tmp_path, "00.png"))])
    settled(qtbot, tab)

    assert not image_of(tab, FOOL)
    assert unsorted_files(created) == ["00.png"]


# -- the fields ------------------------------------------------------------------------------


def test_editing_the_name_and_tabbing_away_saves_it_and_retitles_the_tab(qtbot, active, created):
    header = active.header
    header.name_edit.setFocus()
    header.name_edit.selectAll()
    qtbot.keyClicks(header.name_edit, "Renamed")

    with qtbot.waitSignal(active.tab_label_changed):
        qtbot.keyClick(header.name_edit, Qt.Key.Key_Tab)
        settled(qtbot, active)

    assert manifest(created)["deck"]["name"] == "Renamed"
    assert active.tab_title() == "Renamed"
    assert active.header is header
    assert header.artist_edit.hasFocus()


def test_return_in_the_name_saves_it(qtbot, active, created):
    header = active.header
    header.name_edit.setFocus()
    header.name_edit.selectAll()
    qtbot.keyClicks(header.name_edit, "Returned")
    qtbot.keyClick(header.name_edit, Qt.Key.Key_Return)
    settled(qtbot, active)

    assert manifest(created)["deck"]["name"] == "Returned"


def test_a_blank_name_restores_the_old_one_and_writes_nothing(qtbot, active, created):
    before = (created / "deck.toml").read_bytes()
    header = active.header
    header.name_edit.setFocus()
    header.name_edit.selectAll()
    qtbot.keyClicks(header.name_edit, "   ")
    qtbot.keyClick(header.name_edit, Qt.Key.Key_Tab)
    settled(qtbot, active)

    assert header.name_edit.text() == "Created"
    assert (created / "deck.toml").read_bytes() == before


def test_escape_restores_the_saved_text(qtbot, active, created):
    before = (created / "deck.toml").read_bytes()
    header = active.header
    header.artist_edit.setFocus()
    qtbot.keyClicks(header.artist_edit, "Someone")
    qtbot.keyClick(header.artist_edit, Qt.Key.Key_Escape)
    header.description_edit.setFocus()
    qtbot.keyClicks(header.description_edit, "Words")
    qtbot.keyClick(header.description_edit, Qt.Key.Key_Escape)
    header.name_edit.setFocus()
    settled(qtbot, active)

    assert header.artist_edit.text() == ""
    assert header.description_edit.toPlainText() == ""
    assert (created / "deck.toml").read_bytes() == before


def test_the_description_takes_newlines_and_saves_on_leaving(qtbot, active, created):
    header = active.header
    header.description_edit.setFocus()
    qtbot.keyClicks(header.description_edit, "One")
    qtbot.keyClick(header.description_edit, Qt.Key.Key_Return)
    qtbot.keyClicks(header.description_edit, "Two")
    header.name_edit.setFocus()
    settled(qtbot, active)

    assert manifest(created)["deck"]["description"] == "One\nTwo"


def test_clearing_the_artist_removes_the_key(qtbot, created, curation_file):
    writer.set_fields(created, artist="Someone")
    tab = shown(qtbot, created)
    with qtbot.waitActive(tab):
        tab.activateWindow()
    settled(qtbot, tab)
    editor = tab.header.artist_edit
    assert editor.text() == "Someone"

    editor.setFocus()
    editor.selectAll()
    qtbot.keyClick(editor, Qt.Key.Key_Delete)
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    settled(qtbot, tab)

    assert "artist" not in manifest(created)["deck"]


def test_a_created_decks_header_has_no_details_toggle_and_no_version(tab):
    header = tab.header
    texts = [label.text() for label in header.findChildren(QLabel)]

    assert header.details_button is None
    assert not [
        button
        for button in header.findChildren(QToolButton)
        if button.text() == DECK_VIEW["details"]
    ]
    assert not any(
        DECK_VIEW["field.version"] in text or DECK_VIEW["field.schema_version"] in text
        for text in texts
    )
    assert writer.FIRST_VERSION not in texts


def test_an_installed_decks_header_has_no_editor_and_keeps_its_toggle(qtbot, curation_file):
    tab = shown(qtbot, MINIMAL_DECK_PATH)

    assert tab.header.details_button is not None
    assert not tab.header.findChildren(InlineLineEdit)
    assert not tab.header.findChildren(InlineTextEdit)
    assert not tab.header.findChildren(QRadioButton)
    assert not hasattr(tab.header, "add_images_button")


def test_the_count_line_has_its_own_bar(qtbot, tab, tmp_path):
    tab.editor.queue.place(FOOL, picture(tmp_path, "fool.png"))
    settled(qtbot, tab)

    assert tab.header.count_bar is not tab.progress_bar
    assert (tab.header.count_bar.value(), tab.header.count_bar.maximum()) == (1, 22)


# -- the Cards choice --------------------------------------------------------------------------


def test_a_new_deck_shows_majors_only(tab):
    assert tab.header.majors_radio.isChecked()
    assert not tab.header.all_radio.isChecked()


def test_all_78_lays_out_the_minors_and_drops_the_exclusion(qtbot, tab, created):
    tab.header.all_radio.click()

    assert not tab.header.all_radio.isEnabled()
    settled(qtbot, tab)

    assert len(tab.deck.cards) == 78
    assert "excluded_cards" not in manifest(created)
    assert tab.header.all_radio.isChecked() and tab.header.all_radio.isEnabled()


def test_majors_only_from_78_returns_22_with_a_placed_minor_in_unsorted(
    qtbot, tab, tmp_path, created
):
    tab.header.all_radio.click()
    settled(qtbot, tab)
    tab.editor.queue.place(TWO_OF_CUPS, picture(tmp_path, "my-two.png"))
    settled(qtbot, tab)

    tab.header.majors_radio.click()
    settled(qtbot, tab)

    assert len(tab.deck.cards) == 22
    assert unsorted_files(created) == ["my-two.png"]
    assert "my-two.png" in tab.editor.unsorted.names()
    assert tab.header.majors_radio.isChecked()


def test_clicking_the_checked_choice_writes_nothing(qtbot, tab, created):
    before = (created / "deck.toml").read_bytes()

    tab.header.majors_radio.click()
    settled(qtbot, tab)

    assert (created / "deck.toml").read_bytes() == before
    assert tab.header.majors_radio.isEnabled()


# -- the cover ----------------------------------------------------------------------------------


def test_an_empty_cover_is_a_well_level_with_the_title(tab):
    header = tab.header
    cover, title = header.cover_label, header.name_edit

    assert cover.text() == ""
    assert cover.empty
    assert cover.accessibleDescription() == DECK_VIEW["no_cover"]
    assert cover.mapTo(header, QPoint(0, 0)).y() == title.mapTo(header, QPoint(0, 0)).y()


def test_a_placed_fool_becomes_the_cover(qtbot, tab, tmp_path):
    tab.editor.queue.place(FOOL, picture(tmp_path, "fool.png"))
    settled(qtbot, tab)

    assert not tab.header.cover_label.empty
    assert tab.header.cover_label.accessibleDescription() == ""


def test_the_manifest_stays_valid_toml_after_edits(qtbot, tab, created):
    tab.editor.queue.set_fields(name="A", artist="B", description="C\nD")
    settled(qtbot, tab)

    parsed = tomlkit.parse((created / "deck.toml").read_text(encoding="utf-8"))
    assert parsed["deck"]["description"] == "C\nD"
    assert tab.header.description_edit.toPlainText() == "C\nD"
