from types import SimpleNamespace

import pytest

from tarot_canvas.ui.library.deck_model import (
    SORT_AUTHOR,
    SORT_COUNT,
    SORT_NAME,
    SORT_RECENT,
    AuthorRole,
    CoverPathRole,
    DeckFilterProxyModel,
    DeckListModel,
    DeckRole,
    SubtitleRole,
    deck_subtitle,
    is_majors_only,
)


def fake_deck(name, author="Unknown", majors=3, minors=0, images=True, path=None):
    def card(index, card_type):
        return {
            "type": card_type,
            "number": index,
            "image": f"/decks/{name}/{card_type}/{index}.png" if images else None,
        }

    cards = [card(i, "major_arcana") for i in range(majors)]
    cards += [card(i, "minor_arcana") for i in range(minors)]
    return SimpleNamespace(
        deck_path=path or f"/decks/{name}",
        get_name=lambda: name,
        get_all_cards=lambda: cards,
        get_cards_by_type=lambda t: [c for c in cards if c["type"] == t],
        _metadata={"deck": {"author": author}},
    )


def test_majors_only_deck_is_labelled():
    deck = fake_deck("Share The Magic", author="Lila Hunnisett", majors=22, minors=0)
    assert is_majors_only(deck)
    assert deck_subtitle(deck) == "22 cards • majors only • Lila Hunnisett"
    assert deck_subtitle(deck, abbreviated=True) == "22 cards • majors"


def test_partial_deck_gets_a_plain_count_not_a_wrong_label():
    """Majors plus one suit is not 'majors only'; a wrong label is worse than none."""
    deck = fake_deck("Partial", majors=22, minors=14)
    assert not is_majors_only(deck)
    assert deck_subtitle(deck) == "36 cards • Unknown"


def test_full_deck_is_not_labelled_majors_only():
    assert not is_majors_only(fake_deck("Full", majors=22, minors=56))


def test_cover_prefers_the_fool_then_falls_back(qapp):
    model = DeckListModel([fake_deck("Deck", majors=3)])
    assert model.data(model.index(0, 0), CoverPathRole).endswith("major_arcana/0.png")


def test_cover_falls_back_to_any_card_with_art(qapp):
    deck = fake_deck("Deck", majors=0)
    deck.get_cards_by_type = lambda t: (
        [{"type": t, "number": 5, "image": "/art/five.png"}] if t == "major_arcana" else []
    )
    model = DeckListModel([deck])
    assert model.data(model.index(0, 0), CoverPathRole) == "/art/five.png"


def test_cover_is_none_when_no_card_has_art(qapp):
    model = DeckListModel([fake_deck("Artless", images=False)])
    assert model.data(model.index(0, 0), CoverPathRole) is None


def test_model_exposes_roles_the_delegate_paints(qapp):
    model = DeckListModel(
        [fake_deck("Rider-Waite-Smith", author="P. C. Smith", majors=22, minors=56)]
    )
    index = model.index(0, 0)
    assert model.data(index) == "Rider-Waite-Smith"
    assert model.data(index, SubtitleRole) == "78 cards • P. C. Smith"
    assert model.data(index, AuthorRole) == "P. C. Smith"
    assert model.data(index, DeckRole).get_name() == "Rider-Waite-Smith"


def test_model_row_count_is_flat(qapp):
    model = DeckListModel([fake_deck("A"), fake_deck("B")])
    assert model.rowCount() == 2
    assert model.rowCount(model.index(0, 0)) == 0


@pytest.fixture
def proxy(qapp):
    decks = [
        fake_deck("Zodiac", author="Alice", majors=22, minors=56),
        fake_deck("Aurora", author="Zeno", majors=22, minors=0),
        fake_deck("Marigold", author="Alice", majors=22, minors=14),
    ]
    model = DeckListModel(decks)
    proxy = DeckFilterProxyModel()
    proxy.setSourceModel(model)
    return proxy


def names(proxy):
    return [proxy.index(row, 0).data() for row in range(proxy.rowCount())]


def test_sort_by_name(proxy):
    proxy.set_sort_key(SORT_NAME)
    assert names(proxy) == ["Aurora", "Marigold", "Zodiac"]


def test_sort_by_author_breaks_ties_by_name(proxy):
    proxy.set_sort_key(SORT_AUTHOR)
    assert names(proxy) == ["Marigold", "Zodiac", "Aurora"]


def test_sort_by_card_count(proxy):
    proxy.set_sort_key(SORT_COUNT)
    assert names(proxy) == ["Aurora", "Marigold", "Zodiac"]


def test_sort_by_recent_puts_newest_first(proxy):
    from tarot_canvas.settings import record_deck_opened

    record_deck_opened("/decks/Marigold", when=100)
    record_deck_opened("/decks/Zodiac", when=200)
    proxy.set_sort_key(SORT_RECENT)
    # Never-opened decks sort last, tied at 0 and ordered A-Z among themselves.
    assert names(proxy) == ["Zodiac", "Marigold", "Aurora"]


def test_search_matches_name_and_author_case_insensitively(proxy):
    proxy.set_sort_key(SORT_NAME)
    proxy.setFilterFixedString("aur")
    assert names(proxy) == ["Aurora"]

    proxy.setFilterFixedString("alice")
    assert names(proxy) == ["Marigold", "Zodiac"]

    proxy.setFilterFixedString("")
    assert len(names(proxy)) == 3
