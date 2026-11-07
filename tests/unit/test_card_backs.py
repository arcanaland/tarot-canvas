import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QImage

from tarot_canvas.models.deck import TarotDeck
from tarot_canvas.models.reference_deck import ReferenceDeck

DECK_TOML = '[deck]\nname = "Backs"\nversion = "1.0.0"\n'
CARD = QSize(60, 100)


def _image(path, colour="red"):
    image = QImage(8, 12, QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    assert image.save(str(path))


def _deck(root, backs=(), default=None):
    root.mkdir(exist_ok=True)
    toml = DECK_TOML
    if default:
        toml += f'\n[card_backs]\ndefault = "{default}"\n'
    (root / "deck.toml").write_text(toml, encoding="utf-8")
    if backs:
        (root / "card_backs").mkdir()
        for name in backs:
            _image(root / "card_backs" / name)
    return TarotDeck(str(root))


# -- discovery ---------------------------------------------------------------------


def test_backs_are_found_over_the_extension_chain(tmp_path, qapp):
    deck = _deck(tmp_path / "d", ["a.jpg", "b.webp", "c.png", "c.jpg"])
    backs, default = deck.get_card_backs()
    assert set(backs) == {"a", "b", "c"}
    assert backs["a"].endswith("a.jpg")
    assert backs["b"].endswith("b.webp")
    assert backs["c"].endswith("c.png")
    assert default == "classic"


def test_other_files_are_not_backs(tmp_path, qapp):
    deck = _deck(tmp_path / "d", ["a.png"])
    (tmp_path / "d" / "card_backs" / "notes.txt").write_text("x")
    assert set(deck.get_card_backs()[0]) == {"a"}


def test_a_deck_without_card_backs_has_none(tmp_path):
    deck = _deck(tmp_path / "d")
    assert deck.get_card_backs() == ({}, "classic")


# -- the retired back ----------------------------------------------------------------


def test_the_retired_back_and_its_empty_folder_go(tmp_path):
    (tmp_path / "card_backs").mkdir()
    (tmp_path / "card_backs" / "classic.jpg").write_bytes(b"x")
    ReferenceDeck.drop_retired_back(tmp_path)
    assert not (tmp_path / "card_backs").exists()


def test_without_the_retired_back_nothing_changes(tmp_path):
    (tmp_path / "deck.toml").write_text("x")
    ReferenceDeck.drop_retired_back(tmp_path)
    ReferenceDeck.drop_retired_back(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["deck.toml"]


def test_only_the_retired_back_goes(tmp_path):
    (tmp_path / "card_backs").mkdir()
    (tmp_path / "card_backs" / "classic.jpg").write_bytes(b"x")
    (tmp_path / "card_backs" / "other.png").write_bytes(b"x")
    ReferenceDeck.drop_retired_back(tmp_path)
    assert [p.name for p in (tmp_path / "card_backs").iterdir()] == ["other.png"]


def test_a_failed_removal_is_logged_not_raised(tmp_path, monkeypatch):
    (tmp_path / "card_backs").mkdir()
    (tmp_path / "card_backs" / "classic.jpg").write_bytes(b"x")

    def refuse(path):
        raise PermissionError(path)

    monkeypatch.setattr("tarot_canvas.models.reference_deck.os.remove", refuse)
    ReferenceDeck.drop_retired_back(tmp_path)
    assert (tmp_path / "card_backs" / "classic.jpg").exists()


def test_the_default_path_is_the_reference_deck(tmp_path, monkeypatch):
    monkeypatch.setattr(ReferenceDeck, "get_reference_deck_path", staticmethod(lambda: tmp_path))
    (tmp_path / "card_backs").mkdir()
    (tmp_path / "card_backs" / "classic.jpg").write_bytes(b"x")
    ReferenceDeck.drop_retired_back()
    assert not (tmp_path / "card_backs").exists()


# -- backs.py ----------------------------------------------------------------------


@pytest.mark.parametrize("backless", [False, True])
def test_no_deck_or_a_backless_one_gets_the_house_back(tmp_path, qapp, backless):
    from tarot_canvas.ui.canvas.backs import back_pixmap

    deck = _deck(tmp_path / "d") if backless else None
    pixmap, is_house = back_pixmap(deck, CARD)
    assert is_house
    assert pixmap.size() == CARD


def test_a_deck_with_a_back_gets_its_own(tmp_path, qapp):
    from tarot_canvas.ui.canvas.backs import back_pixmap

    deck = _deck(tmp_path / "d", ["mine.png"])
    pixmap, is_house = back_pixmap(deck, CARD)
    assert not is_house
    assert pixmap.size() == CARD
    assert pixmap.toImage().pixelColor(30, 50) == QColor("red")


def test_the_default_back_is_preferred(tmp_path, qapp):
    from tarot_canvas.ui.canvas.backs import back_path

    deck = _deck(tmp_path / "d", ["a.png", "b.png"], default="b")
    assert back_path(deck).endswith("b.png")
    deck = _deck(tmp_path / "e", ["a.png", "b.png"], default="z")
    assert back_path(deck).endswith("a.png")


def test_the_house_back_is_drawn_once_per_size(qapp):
    from tarot_canvas.ui.canvas.backs import HOUSE_FILL, house_back

    first = house_back(QSize(61, 101))
    assert house_back(QSize(61, 101)).cacheKey() == first.cacheKey()
    assert house_back(QSize(62, 101)).cacheKey() != first.cacheKey()
    # Plum between the edge and the icon
    assert first.toImage().pixelColor(10, 10) == HOUSE_FILL


def test_the_reference_deck_once_dropped_wears_the_house_back(tmp_path, qapp):
    from tarot_canvas.ui.canvas.backs import back_pixmap

    root = tmp_path / "rider-waite-smith"
    _deck(root, ["classic.jpg"])
    ReferenceDeck.drop_retired_back(root)
    assert back_pixmap(TarotDeck(str(root)), CARD)[1]
