import pytest
from PyQt6.QtCore import Qt

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.ui import typography
from tarot_canvas.ui.deck_view.card_model import KIND_CARD, CardModel, CardRole, KindRole
from tarot_canvas.ui.deck_view.tableau_model import (
    KIND_GHOST,
    KIND_LABEL,
    ROW_CARDS,
    ROW_GAP,
    ROW_LABELS,
    DimmedRole,
    TableauModel,
)
from tests.conftest import write_full_deck


def tableau(deck):
    return TableauModel(CardModel(deck))


def card_id(model, row, column):
    card = model.index(row, column).data(CardRole)
    return card["id"] if card else None


def kind(model, row, column):
    return model.index(row, column).data(KindRole)


def label_row(model):
    return [model.row_kind(row) for row in range(model.rowCount())].index(ROW_LABELS)


def deck_without(tmp_path, *card_ids):
    root = write_full_deck(tmp_path / "missing")
    excluded = ", ".join(f'"{card}"' for card in card_ids)
    (root / "deck.toml").write_text(
        '[deck]\nname = "Missing"\nversion = "1.0.0"\n\n'
        f'[deck.excluded_cards]\nreason = "test"\ncards = [{excluded}]\n',
        encoding="utf-8",
    )
    return TarotDeck(str(root))


def test_the_fool_heads_three_rows_of_seven(full_deck):
    model = tableau(full_deck)

    assert model.columnCount() == 7
    assert card_id(model, 0, 3) == "major_arcana.00"
    assert card_id(model, 1, 0) == "major_arcana.01"
    assert card_id(model, 1, 6) == "major_arcana.07"
    assert card_id(model, 2, 0) == "major_arcana.08"
    assert card_id(model, 3, 6) == "major_arcana.21"
    assert all(kind(model, 0, column) is None for column in (0, 1, 2, 4, 5, 6))


def test_a_gap_then_suits_over_columns_and_ranks_down_the_side(full_deck):
    model = tableau(full_deck)
    labels = label_row(model)

    assert model.row_kind(labels - 1) == ROW_GAP
    assert [model.index(labels, column).data() or "" for column in range(1, 6)] == [
        "",
        "Wands",
        "Cups",
        "Swords",
        "Pentacles",
    ]
    assert card_id(model, labels + 1, 2) == "minor_arcana.wands.ace"
    assert model.index(labels + 1, 1).data() == "Ace"
    assert model.index(labels + 14, 1).data() == "King"
    assert card_id(model, labels + 14, 5) == "minor_arcana.pentacles.king"
    assert model.rowCount() == labels + 15
    assert all(model.row_kind(row) == ROW_CARDS for row in range(labels + 1, labels + 15))


def test_labels_are_deck_data_in_their_roles(full_deck):
    model = tableau(full_deck)
    labels = label_row(model)
    suit = model.index(labels, 2)
    rank = model.index(labels + 1, 1)

    assert suit.data(KindRole) == rank.data(KindRole) == KIND_LABEL
    assert suit.data(Qt.ItemDataRole.FontRole) == typography.font(typography.Role.HEADING_3)
    assert rank.data(Qt.ItemDataRole.FontRole) == typography.font(typography.Role.SMALL)
    assert rank.data(Qt.ItemDataRole.TextAlignmentRole) & Qt.AlignmentFlag.AlignRight
    assert suit.data(Qt.ItemDataRole.TextAlignmentRole) & Qt.AlignmentFlag.AlignHCenter
    assert model.index(labels + 11, 1).data() == full_deck.get_display_court_name("page")
    assert model.flags(suit) == model.flags(rank) == Qt.ItemFlag.NoItemFlags


def test_a_missing_card_is_a_ghost_and_nothing_moves(tmp_path, full_deck):
    full = tableau(full_deck)
    model = tableau(deck_without(tmp_path, "minor_arcana.cups.three"))
    labels = label_row(model)

    assert kind(model, labels + 3, 3) == KIND_GHOST
    assert model.flags(model.index(labels + 3, 3)) == Qt.ItemFlag.NoItemFlags
    for row in range(model.rowCount()):
        for column in range(model.columnCount()):
            if (row, column) != (labels + 3, 3):
                assert card_id(model, row, column) == card_id(full, row, column)


def test_a_missing_major_is_a_ghost_in_its_slot(tmp_path):
    model = tableau(deck_without(tmp_path, "major_arcana.00", "major_arcana.12"))

    assert kind(model, 0, 3) == KIND_GHOST
    assert kind(model, 2, 4) == KIND_GHOST
    assert card_id(model, 2, 3) == "major_arcana.11"


def test_majors_take_their_slots_by_number(full_deck):
    strength = full_deck.get_card_by_id("major_arcana.08")
    justice = full_deck.get_card_by_id("major_arcana.11")
    strength["number"], justice["number"] = 11, 8
    model = tableau(full_deck)

    assert card_id(model, 2, 0) == "major_arcana.11"
    assert card_id(model, 2, 3) == "major_arcana.08"


def test_a_fifth_suit_takes_a_fifth_column(full_deck):
    full_deck._cards.extend(
        {
            "id": f"minor_arcana.stars.{rank}",
            "name": f"{rank} of Stars",
            "type": "minor_arcana",
            "suit": "stars",
            "rank": rank,
        }
        for rank in ("ace", "two")
    )
    model = tableau(full_deck)
    labels = label_row(model)

    assert model.columnCount() == 7
    assert model.index(labels, 6).data() == full_deck.get_display_suit_name("stars")
    assert model.index(labels + 1, 1).data() == "Ace"
    assert card_id(model, labels + 1, 6) == "minor_arcana.stars.ace"
    # Not a canonical slot, so not a ghost
    assert kind(model, labels + 3, 6) is None


def test_a_deck_without_suits_has_no_minor_block(full_deck):
    full_deck._cards[:] = [c for c in full_deck._cards if c["type"] == "major_arcana"]
    model = tableau(full_deck)

    assert model.rowCount() == 4


def test_every_card_cell_maps_to_its_card_and_back(full_deck):
    model = tableau(full_deck)
    cells = model.card_cells()

    assert len(cells) == 78
    for row, column in cells:
        index = model.index(row, column)
        source = model.mapToSource(index)
        assert source.data(CardRole)["id"] == index.data(CardRole)["id"]
        assert model.mapFromSource(source) == index
    assert not model.mapToSource(model.index(0, 0)).isValid()


@pytest.mark.parametrize(
    ("text", "dimmed"), [("", False), ("FOOL", False), ("0", False), ("king", True), ("KoW", True)]
)
def test_find_dims_the_cards_it_does_not_match(full_deck, text, dimmed):
    model = tableau(full_deck)
    model.set_find(text)

    assert model.index(0, 3).data(DimmedRole) is dimmed
    assert model.index(0, 3).data(KindRole) == KIND_CARD


def test_find_never_dims_a_label(full_deck):
    model = tableau(full_deck)
    model.set_find("zzz")
    labels = label_row(model)

    assert not model.index(labels, 2).data(DimmedRole)
    assert not model.index(labels + 1, 1).data(DimmedRole)
