"""The deck view's models for a deck created in the app: every slot, and the back"""

import os

import pytest
from PyQt6.QtGui import QColor, QImage

from tarot_canvas.models import deck_writer as writer
from tarot_canvas.models.arcana_backend import load_deck
from tarot_canvas.models.card_search import Query
from tarot_canvas.ui.deck_view.card_model import (
    KIND_BACK,
    KIND_CARD,
    BackPathRole,
    CardModel,
    CardRole,
    EmptySlotRole,
    KindRole,
    SlotIdRole,
    display_rows,
)
from tarot_canvas.ui.deck_view.tableau_model import KIND_LABEL, MAJOR_COLUMNS, TableauModel
from tarot_canvas.ui.library.decks.model import created_progress


@pytest.fixture
def decks_root(tmp_path, curation_file):
    return tmp_path / "decks"


@pytest.fixture
def full(decks_root):
    return writer.create("Full", majors_only=False, decks_root=decks_root)


@pytest.fixture
def majors(decks_root):
    return writer.create("Majors", majors_only=True, decks_root=decks_root)


def picture(tmp_path, name="art.png"):
    image = QImage(60, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    path = tmp_path / name
    assert image.save(os.fspath(path))
    return path


def kinds(model):
    return [model.index(row, 0).data(KindRole) for row in range(model.rowCount())]


def cells(model, kind):
    return [
        (row, column)
        for row in range(model.rowCount())
        for column in range(model.columnCount())
        if model.index(row, column).data(KindRole) == kind
    ]


def test_an_editable_full_deck_lays_out_78_cards_and_the_back_last(full, qapp):
    model = CardModel(load_deck(os.fspath(full)), editable=True)

    assert kinds(model).count(KIND_CARD) == 78
    assert kinds(model)[-1] == KIND_BACK
    assert kinds(model).count(KIND_BACK) == 1

    tableau = TableauModel(model)
    assert len(cells(tableau, KIND_CARD)) == 78
    left = (tableau.columnCount() - MAJOR_COLUMNS) // 2
    assert cells(tableau, KIND_BACK) == [(0, left)]


def test_an_editable_majors_only_deck_lays_out_22_cards_the_back_and_no_suit_labels(majors, qapp):
    model = CardModel(load_deck(os.fspath(majors)), editable=True)
    tableau = TableauModel(model)

    assert kinds(model).count(KIND_CARD) == 22
    assert len(cells(tableau, KIND_CARD)) == 22
    assert len(cells(tableau, KIND_BACK)) == 1
    assert cells(tableau, KIND_LABEL) == []


def test_the_back_is_not_a_card_and_find_never_matches_it(full, qapp):
    model = CardModel(load_deck(os.fspath(full)), editable=True)
    back = model.index(model.back_row(), 0)

    assert back.data(CardRole) is None
    assert back.data(BackPathRole) is None
    assert not model.matches(model.back_row(), Query("back"))


def test_a_deck_not_created_here_has_the_rows_and_cells_it_had(full_deck, qapp):
    plain = CardModel(full_deck)
    flagged = CardModel(full_deck, editable=False)
    assert plain.rowCount() == flagged.rowCount() == len(display_rows(full_deck))
    assert kinds(plain) == kinds(flagged)
    assert KIND_BACK not in kinds(plain)

    a, b = TableauModel(plain), TableauModel(flagged)
    assert (a.rowCount(), a.columnCount()) == (b.rowCount(), b.columnCount())
    for kind in (KIND_CARD, KIND_LABEL, KIND_BACK):
        assert cells(a, kind) == cells(b, kind)
    assert cells(a, KIND_BACK) == []


def test_set_deck_with_a_placed_card_keeps_the_rows_and_rebuilds_the_tableau(
    full, tmp_path, qapp, qtbot
):
    model = CardModel(load_deck(os.fspath(full)), editable=True)
    tableau = TableauModel(model)
    rows = model.rowCount()
    writer.place(full, "major_arcana.00", picture(tmp_path))
    writer.place(full, writer.BACK, picture(tmp_path, "back.png"))

    with qtbot.waitSignal(tableau.modelReset):
        model.set_deck(load_deck(os.fspath(full)))

    assert model.rowCount() == rows
    fool = next(
        tableau.index(*cell)
        for cell in cells(tableau, KIND_CARD)
        if tableau.index(*cell).data(CardRole).canonical_id == "major_arcana.00"
    )
    assert fool.data(CardRole).default_image()
    assert tableau.index(*cells(tableau, KIND_BACK)[0]).data(BackPathRole)


def test_created_progress_counts_cards_and_not_the_back(full, majors, tmp_path, qapp):
    assert created_progress(load_deck(os.fspath(full))) == (0, 78)
    assert created_progress(load_deck(os.fspath(majors))) == (0, 22)

    writer.place(majors, "major_arcana.00", picture(tmp_path))
    writer.place(majors, writer.BACK, picture(tmp_path, "back.png"))

    assert created_progress(load_deck(os.fspath(majors))) == (1, 22)


def test_each_slot_names_its_writer_id_and_whether_it_is_empty(majors, tmp_path, qapp):
    fool = "major_arcana.00"
    writer.place(majors, fool, picture(tmp_path))
    model = CardModel(load_deck(os.fspath(majors)), editable=True)
    tableau = TableauModel(model)

    fool_row, back_row = model.row_of(fool), model.row_of(writer.BACK)
    assert model.index(fool_row, 0).data(SlotIdRole) == fool
    assert back_row == model.back_row()
    assert model.row_of("major_arcana.99") is None
    heading = model.index(0, 0)
    assert heading.data(SlotIdRole) is None and heading.data(EmptySlotRole) is False

    assert model.index(fool_row, 0).data(EmptySlotRole) is False
    assert model.index(model.row_of("major_arcana.01"), 0).data(EmptySlotRole) is True
    assert model.index(back_row, 0).data(EmptySlotRole) is True
    # The tableau's cells answer for their card
    back_cell = tableau.mapFromSource(model.index(back_row, 0))
    assert back_cell.data(SlotIdRole) == writer.BACK
    assert back_cell.data(EmptySlotRole) is True


def test_a_deck_not_created_here_has_no_empty_slots(majors, qapp):
    model = CardModel(load_deck(os.fspath(majors)), editable=False)

    rows = model.card_rows()
    assert all(model.index(row, 0).data(EmptySlotRole) is False for row in rows)
    assert model.row_of(writer.BACK) is None
