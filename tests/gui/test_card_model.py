"""The deck view's card model, and the delegate that paints it"""

import threading
from types import SimpleNamespace

import pytest
from PyQt6 import sip
from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from tarot_canvas.models.card_ids import COURTS, PIPS
from tarot_canvas.ui.canvas import detail
from tarot_canvas.ui.deck_view import card_delegate
from tarot_canvas.ui.deck_view.card_delegate import CardDelegate
from tarot_canvas.ui.deck_view.card_model import (
    KIND_CARD,
    KIND_HEADING,
    KIND_NOTE,
    CardModel,
    CardRole,
    KindRole,
)
from tarot_canvas.ui.deck_view.sections_view import SectionsView
from tarot_canvas.ui.library import units
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab

# Some aspect ratios from my personal decks
CARD_SIZES = [(600, 1024), (1140, 1140), (2420, 1400)]


@pytest.fixture(autouse=True)
def drained_pool():
    """No decode from one test may land in the next."""
    yield
    QThreadPool.globalInstance().waitForDone()


def rows(model):
    return [
        (model.index(row, 0).data(KindRole), model.index(row, 0).data())
        for row in range(model.rowCount())
    ]


# -- the model ----------------------------------------------------------------------


def test_the_majors_come_first_by_number_then_each_suit_ace_to_king(full_deck):
    model = CardModel(full_deck)
    kinds = [kind for kind, _ in rows(model)]
    cards = [model.index(row, 0).data(CardRole) for row in model.card_rows()]

    assert rows(model)[0] == (KIND_HEADING, "Major Arcana")
    assert [card["number"] for card in cards[:22]] == list(range(22))
    headings = [text for kind, text in rows(model) if kind == KIND_HEADING]
    assert headings == ["Major Arcana", "Wands", "Cups", "Swords", "Pentacles"]
    for suit_index, suit in enumerate(["wands", "cups", "swords", "pentacles"]):
        suit_cards = cards[22 + 14 * suit_index : 22 + 14 * (suit_index + 1)]
        assert [card["suit"] for card in suit_cards] == [suit] * 14
        assert [card["rank"] for card in suit_cards] == list(PIPS + COURTS)
    assert kinds.count(KIND_CARD) == 78
    assert len(kinds) == 78 + 5


def test_the_card_rows_are_every_row_but_the_headings(full_deck):
    model = CardModel(full_deck)
    assert model.card_rows() == [
        row for row in range(model.rowCount()) if model.index(row, 0).data(KindRole) == KIND_CARD
    ]
    assert model.deck is full_deck


def test_headings_and_notes_have_no_flags(full_deck, minimal_deck):
    for deck in (full_deck, minimal_deck):
        model = CardModel(deck)
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            if index.data(KindRole) == KIND_CARD:
                assert model.flags(index) == (
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
            else:
                assert model.flags(index) == Qt.ItemFlag.NoItemFlags


def test_a_deck_with_no_suits_says_why_in_a_note(minimal_deck):
    assert rows(CardModel(minimal_deck)) == [
        (KIND_HEADING, "Major Arcana"),
        (KIND_CARD, "The Fool"),
        (KIND_CARD, "The Magician"),
        (KIND_NOTE, "Note: Test fixture only needs enough cards to exercise the loader."),
    ]


def test_a_major_with_no_number_goes_last(minimal_deck):
    unnumbered = {"id": "x", "name": "Unnumbered", "type": "major_arcana"}
    deck = SimpleNamespace(
        get_cards_by_type=lambda kind: [unnumbered, *minimal_deck.get_cards_by_type(kind)],
        get_suits=lambda: [],
        get_exclusion_reason=lambda: None,
    )
    assert [text for _, text in rows(CardModel(deck))] == [
        "Major Arcana",
        "The Fool",
        "The Magician",
        "Unnumbered",
    ]


# -- the delegate -------------------------------------------------------------------


def _art_deck(tmp_path, width, height):
    """A deck of one major whose art is width x height of red"""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    path = tmp_path / f"card-{width}x{height}.png"
    assert image.save(str(path))
    return _one_card_deck({"name": "Test Card", "image": str(path), "type": "major_arcana"})


def _one_card_deck(card):
    card = {"id": "major_arcana.00", "number": 0, **card}
    return SimpleNamespace(
        get_cards_by_type=lambda kind: [card] if kind == "major_arcana" else [],
        get_suits=lambda: [],
        get_exclusion_reason=lambda: None,
    )


def _view(qtbot, deck):
    view = SectionsView()
    view.setModel(CardModel(deck, view))
    view.setItemDelegate(CardDelegate(view, density=units.DENSITY_MEDIUM))
    view.resize(400, 400)
    qtbot.addWidget(view)
    view.show()
    qtbot.waitExposed(view)
    return view


def _first_card(view):
    return view.model().index(view.model().card_rows()[0], 0)


def _pixmaps(delegate):
    return [pixmap for pixmap in delegate._art._pixmaps.values() if pixmap is not None]


def _painted_art_size(view):
    """Size of the card art as actually painted"""
    rect = view.visualRect(_first_card(view))
    image = view.viewport().grab(rect).toImage().convertToFormat(QImage.Format.Format_RGB32)
    red = QColor("red").rgb()
    hits = [
        (x, y)
        for x in range(image.width())
        for y in range(image.height())
        if image.pixel(x, y) == red
    ]
    assert hits, "card art was not painted"
    xs, ys = zip(*hits, strict=True)
    return max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


@pytest.mark.parametrize(("width", "height"), CARD_SIZES)
def test_painted_art_keeps_the_card_aspect_ratio(qtbot, tmp_path, width, height):
    view = _view(qtbot, _art_deck(tmp_path, width, height))
    qtbot.waitUntil(lambda: bool(_pixmaps(view.itemDelegate())))
    view.viewport().grab()

    painted_width, painted_height = _painted_art_size(view)
    # Loose: the hairline border covers the art's outermost pixels
    assert painted_width / painted_height == pytest.approx(width / height, rel=0.03)


@pytest.mark.parametrize(("width", "height"), CARD_SIZES)
def test_art_fits_inside_its_well(qtbot, tmp_path, width, height):
    view = _view(qtbot, _art_deck(tmp_path, width, height))
    qtbot.waitUntil(lambda: bool(_pixmaps(view.itemDelegate())))

    (pixmap,) = _pixmaps(view.itemDelegate())
    well = view.itemDelegate().cover_size()
    size = pixmap.deviceIndependentSize().toSize()
    assert size.width() <= well.width()
    assert size.height() <= well.height()
    assert size.width() == well.width() or size.height() == well.height()


def test_missing_art_paints_the_placeholder_and_asks_once(qtbot, tmp_path, monkeypatch):
    requests, wells = [], []
    monkeypatch.setattr(detail.ArtLoader, "request", lambda *args: requests.append(args))
    monkeypatch.setattr(
        card_delegate, "paint_placeholder_well", lambda painter, well, palette: wells.append(well)
    )
    view = _view(qtbot, _one_card_deck({"name": "Test Card", "image": str(tmp_path / "nope.png")}))
    view.viewport().grab()
    view.viewport().grab()

    assert requests == []
    assert len(wells) >= 2
    assert wells[0].size() == view.itemDelegate().cover_size()


def test_a_card_with_no_art_at_all_paints_the_placeholder(qtbot, monkeypatch):
    wells = []
    monkeypatch.setattr(
        card_delegate, "paint_placeholder_well", lambda painter, well, palette: wells.append(well)
    )
    view = _view(qtbot, _one_card_deck({"name": "Test Card", "image": None}))
    view.viewport().grab()
    assert wells


def _held_art(monkeypatch):
    release = threading.Event()
    read_art = detail.read_art

    def held_read_art(*args):
        release.wait(5)
        return read_art(*args)

    monkeypatch.setattr(detail, "read_art", held_read_art)
    return release


def test_a_view_deleted_before_its_art_lands_is_skipped(qtbot, tmp_path, monkeypatch):
    release = _held_art(monkeypatch)
    view = _view(qtbot, _art_deck(tmp_path, 600, 1024))
    view.viewport().grab()
    sip.delete(view)

    release.set()
    QThreadPool.globalInstance().waitForDone()
    QApplication.processEvents()


def test_the_deck_view_appears_before_its_art_is_decoded(qtbot, monkeypatch, full_deck):
    release = _held_art(monkeypatch)
    tab = DeckViewTab(full_deck.deck_path)
    qtbot.addWidget(tab)
    tab.resize(900, 600)
    tab.show()
    qtbot.waitExposed(tab)
    tab.grid.viewport().grab()

    assert tab.grid.isVisible()
    assert not _pixmaps(tab.delegate)

    release.set()
    QThreadPool.globalInstance().waitForDone()
    qtbot.waitUntil(lambda: bool(_pixmaps(tab.delegate)))


def test_a_density_change_forgets_the_art(qtbot, tmp_path):
    view = _view(qtbot, _art_deck(tmp_path, 600, 1024))
    qtbot.waitUntil(lambda: bool(_pixmaps(view.itemDelegate())))

    assert view.itemDelegate().set_density(units.DENSITY_LARGE)
    assert not _pixmaps(view.itemDelegate())


def test_headings_span_the_view(qtbot, full_deck):
    view = _view(qtbot, full_deck)
    heading = view.model().index(0, 0)
    width = view.viewport().width() - 2 * view.spacing()
    assert view.visualRect(heading).width() == width
