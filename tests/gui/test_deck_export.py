"""Export…: the fields, empty cards left out, the gate, and Put back"""

import os
import tomllib
import zipfile

import pytest
from PyQt6.QtWidgets import QDialog

from tarot_canvas.models import deck_writer as writer
from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS
from tarot_canvas.models.deck_container import unpack_container
from tarot_canvas.models.deck_validation import Finding, Level, LoadError, Verdict
from tarot_canvas.ui.deck_view import exporter
from tarot_canvas.ui.deck_view.export_dialogs import ExportFieldsDialog, FindingsDialog
from tarot_canvas.ui.strings import DECK_VIEW, LIBRARY
from tests.gui.test_handmade_deck_view import picture, settled, shown

MAJORS = [card for card in CANONICAL_CARD_IDS if card.startswith("major_arcana.")]
MINORS = [card for card in CANONICAL_CARD_IDS if card.startswith("minor_arcana.")]
COURTS = [
    card
    for card in CANONICAL_CARD_IDS
    if card.rsplit(".", 1)[1] in ("page", "knight", "queen", "king")
]


@pytest.fixture
def staging(tmp_path, monkeypatch):
    root = tmp_path / "staging"
    monkeypatch.setattr(exporter, "get_staging_directory", lambda: root)
    return root


@pytest.fixture
def dialogs(tmp_path, monkeypatch, staging):
    """Answers Export's dialogs; what they were shown is kept"""
    state = {
        "accept": True,
        "fields": {},
        "save_as": tmp_path / "out" / "exported",
        "fields_dialogs": [],
        "findings": [],
        "suggested": [],
    }
    state["save_as"].parent.mkdir()

    def fields_exec(dialog):
        state["fields_dialogs"].append(
            {
                "empty": dialog.empty_list.count() if dialog.empty_list else 0,
                "label": dialog.empty_label.text() if dialog.empty_list else None,
            }
        )
        if "version" in state["fields"]:
            dialog.version_edit.setText(state["fields"]["version"])
        return QDialog.DialogCode.Accepted if state["accept"] else QDialog.DialogCode.Rejected

    def findings_exec(dialog):
        state["findings"].append(dialog)
        return 0

    def save(_parent, _title, suggested, _filter):
        state["suggested"].append(suggested)
        return (os.fspath(state["save_as"]) if state["save_as"] else "", "")

    monkeypatch.setattr(exporter.ExportFieldsDialog, "exec", fields_exec)
    monkeypatch.setattr(exporter.FindingsDialog, "exec", findings_exec)
    monkeypatch.setattr(exporter.QFileDialog, "getSaveFileName", save)
    return state


def made(tmp_path, majors_only=True, placed=()):
    deck = writer.create("Exported", majors_only=majors_only, decks_root=tmp_path / "decks")
    for card_id in placed:
        writer.place(deck, card_id, picture(tmp_path, f"{card_id}.png"))
    return deck


def manifest(deck):
    return tomllib.loads((deck / "deck.toml").read_text(encoding="utf-8"))


def exported(qtbot, tab):
    messages = []
    tab.message.connect(messages.append)
    tab.header.export_button.click()
    qtbot.waitUntil(lambda: not tab.exporter.running and not tab.editor.is_busy())
    return messages


def container_files(path):
    with zipfile.ZipFile(path) as archive:
        return archive.namelist(), tomllib.loads(archive.read("deck.toml").decode())


def test_empty_cards_are_left_out_of_the_export_and_stay_in_the_deck(
    qtbot, tmp_path, curation_file, dialogs
):
    deck = made(tmp_path, placed=MAJORS[:3])
    tab = settled(qtbot, shown(qtbot, deck))
    before = manifest(deck)

    messages = exported(qtbot, tab)

    assert dialogs["fields_dialogs"] == [
        {"empty": 19, "label": DECK_VIEW["export_empty"].format(count=19)}
    ]
    target = dialogs["save_as"].with_name("exported.tarotdeck")
    assert messages == [DECK_VIEW["export_done"].format(file=target.name)]
    names, packed = container_files(target)
    assert sorted(packed["excluded_cards"]["cards"]) == sorted(MINORS + MAJORS[3:])
    assert not [name for name in names if name.startswith(("source/", "unsorted/"))]
    assert manifest(deck) == before
    assert tab.header.cards.majors_radio.isChecked()
    assert tab.header.fill.label.text() == DECK_VIEW["fill_count"].format(placed=3, expected=22)
    assert list(staging_contents(tab)) == []


def staging_contents(tab):
    root = exporter.get_staging_directory()
    return root.iterdir() if root.is_dir() else []


def test_cancelling_the_fields_writes_nothing(qtbot, tmp_path, curation_file, dialogs):
    deck = made(tmp_path, placed=MAJORS[:3])
    tab = settled(qtbot, shown(qtbot, deck))
    before = (deck / "deck.toml").read_bytes()
    dialogs["accept"] = False

    exported(qtbot, tab)

    assert (deck / "deck.toml").read_bytes() == before
    assert not any(dialogs["save_as"].parent.iterdir())
    assert list(staging_contents(tab)) == []


def test_a_changed_version_is_written_and_the_identifier_is_not(
    qtbot, tmp_path, curation_file, dialogs
):
    deck = made(tmp_path, majors_only=True, placed=MAJORS)
    writer.place_unsorted(deck, picture(tmp_path, "loose.png"))
    identifier = manifest(deck)["deck"]["identifier"]
    tab = settled(qtbot, shown(qtbot, deck))
    writer.set_fields(deck, artist="Someone")
    dialogs["fields"] = {"version": "1.0.0"}

    exported(qtbot, tab)

    assert dialogs["fields_dialogs"][0]["empty"] == 0
    assert dialogs["suggested"][0].endswith("exported-1.0.0.tarotdeck")
    target = dialogs["save_as"].with_name("exported.tarotdeck")
    names, packed = container_files(target)
    for table in (manifest(deck)["deck"], packed["deck"]):
        assert table["version"] == "1.0.0"
        assert table["artist"] == "Someone"
        assert table["identifier"] == identifier
    assert not [name for name in names if name.startswith(("source/", "unsorted/"))]
    unpacked = tmp_path / "unpacked"
    unpacked.mkdir()
    unpack_container(target, unpacked)


def test_an_error_shows_the_findings_and_writes_no_file(qtbot, tmp_path, curation_file, dialogs):
    deck = made(tmp_path, placed=MAJORS)
    path = deck / "deck.toml"
    path.write_text(
        path.read_text(encoding="utf-8") + '\n[card_backs]\ndefault = "nope"\n', encoding="utf-8"
    )
    tab = settled(qtbot, shown(qtbot, deck))

    exported(qtbot, tab)

    assert len(dialogs["findings"]) == 1
    assert dialogs["suggested"] == []
    assert not any(dialogs["save_as"].parent.iterdir())
    assert list(staging_contents(tab)) == []


def test_cancelling_the_save_dialog_writes_nothing(qtbot, tmp_path, curation_file, dialogs):
    deck = made(tmp_path, placed=MAJORS)
    tab = settled(qtbot, shown(qtbot, deck))
    dialogs["save_as"] = None

    exported(qtbot, tab)

    assert len(dialogs["suggested"]) == 1
    assert not any((tmp_path / "out").iterdir())
    assert list(staging_contents(tab)) == []


def test_export_waits_for_queued_writes(qtbot, tmp_path, curation_file, dialogs):
    deck = made(tmp_path)
    tab = settled(qtbot, shown(qtbot, deck))
    assert tab.header.export_button.isEnabled()

    tab.editor.queue.place(MAJORS[0], picture(tmp_path, "fool.png"))

    assert not tab.header.export_button.isEnabled()
    settled(qtbot, tab)
    assert tab.header.export_button.isEnabled()


def test_a_complete_deck_stays_complete_after_an_export_leaves_its_empty_cards_out(
    qtbot, tmp_path, curation_file, dialogs
):
    deck = made(tmp_path, majors_only=False, placed=MAJORS + COURTS)
    tab = settled(qtbot, shown(qtbot, deck))

    exported(qtbot, tab)

    _names, packed = container_files(dialogs["save_as"].with_name("exported.tarotdeck"))
    assert len(packed["excluded_cards"]["cards"]) == 56 - 16
    assert "excluded_cards" not in manifest(deck)
    assert tab.header.cards.all_radio.isChecked()
    assert len(tab.deck.cards) == 78


def test_the_findings_dialog_groups_by_card_and_hides_details(qtbot, minimal_deck):
    verdict = Verdict(
        None,
        (
            Finding(Level.ERROR, "e1", "bad two", card="major_arcana.21", spec_url="https://x/1"),
            Finding(Level.ERROR, "e2", "bad zero", card="major_arcana.00", key="cards.x"),
            Finding(Level.WARNING, "w1", "deck warning"),
            Finding(Level.INFO, "i1", "an info", card="major_arcana.00"),
        ),
        75,
    )
    dialog = FindingsDialog(verdict, minimal_deck)
    qtbot.addWidget(dialog)
    tree = dialog.tree

    tops = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    assert tops[0].text(0) == DECK_VIEW["export_deck_level"]
    assert [top.text(0) for top in tops[1:]] == [
        minimal_deck.find_card("major_arcana.00").display_name,
        "major_arcana.21",  # not in the deck, so its ID
    ]
    fool = tops[1]
    assert [fool.child(i).text(0) for i in range(fool.childCount())] == ["bad zero", "an info"]
    assert fool.child(0).text(1) == "e2 · cards.x"
    assert fool.child(1).isHidden()
    assert tops[2].child(0).toolTip(0) == "https://x/1"

    dialog.details_box.setChecked(True)
    assert not fool.child(1).isHidden()
    assert dialog.coverage.text() == DECK_VIEW["export_unchecked"].format(count=75)


def test_a_load_error_is_one_line_with_no_tree(qtbot, minimal_deck):
    dialog = FindingsDialog(Verdict(LoadError("parse_error", "broken"), (), 75), minimal_deck)
    qtbot.addWidget(dialog)

    assert dialog.tree is None
    assert dialog.load_error_label.text() == DECK_VIEW["export_load_error"].format(
        code="parse_error", message="broken"
    )


# -- The fields dialog ---------------------------------------------------------------------


def fields_dialog(qtbot, tab, empty=()):
    dialog = ExportFieldsDialog(tab.deck, list(empty), tab)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog


def test_the_fields_dialog_shows_the_deck_and_asks_only_the_version(qtbot, tmp_path, curation_file):
    deck = made(tmp_path, placed=MAJORS[:1])
    writer.set_fields(deck, artist="Someone", description="Line one\nLine two")
    tab = settled(qtbot, shown(qtbot, deck))

    dialog = fields_dialog(qtbot, tab)

    assert dialog.name_label.full_text() == "Exported"
    assert dialog.artist_label.full_text() == "Someone"
    assert dialog.description_label.full_text() == "Line one\nLine two"
    assert dialog.description_label.text() == "Line one\nLine two"
    assert dialog.focusWidget() is dialog.export_button
    assert dialog.empty_list is None
    assert dialog.changed_fields() == {}
    dialog.version_edit.setText(" 1.0.0 ")
    assert dialog.changed_fields() == {"version": "1.0.0"}
    dialog.version_edit.setText("")
    assert not dialog.export_button.isEnabled()


def test_a_blank_artist_reads_as_the_librarys_unknown(qtbot, tmp_path, curation_file):
    tab = settled(qtbot, shown(qtbot, made(tmp_path)))

    dialog = fields_dialog(qtbot, tab)

    assert dialog.artist_label.full_text() == LIBRARY["unknown_author"]
    assert not dialog.description_label.isVisibleTo(dialog)


def test_a_long_description_does_not_make_the_dialog_taller(qtbot, tmp_path, curation_file):
    deck = made(tmp_path)
    tab = settled(qtbot, shown(qtbot, deck))
    short = fields_dialog(qtbot, tab).height()

    writer.set_fields(deck, description="word " * 400)
    tab = settled(qtbot, shown(qtbot, deck))
    dialog = fields_dialog(qtbot, tab)

    assert dialog.height() == short
    assert dialog.description_label.text().endswith("…")
    assert dialog.description_label.toolTip().startswith("word word")


def test_the_empty_cards_are_listed_only_when_asked(qtbot, tmp_path, curation_file):
    tab = settled(qtbot, shown(qtbot, made(tmp_path, placed=MAJORS[:3])))
    empty = [card for card in tab.deck.cards if not card.default_image()]

    dialog = fields_dialog(qtbot, tab, empty)

    assert dialog.empty_label.text() == DECK_VIEW["export_empty"].format(count=19)
    assert not dialog.empty_list.isVisibleTo(dialog)
    dialog.empty_toggle.click()
    assert dialog.empty_list.isVisibleTo(dialog)
    assert dialog.empty_list.count() == 19
