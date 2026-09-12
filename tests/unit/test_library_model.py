from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QLocale, Qt

from tarot_canvas.models.catalog import parse_index
from tarot_canvas.ui.library.deck_downloads import DeckState, deck_downloads
from tarot_canvas.ui.library.deck_model import (
    SORT_AUTHOR,
    SORT_COUNT,
    SORT_NAME,
    SORT_RECENT,
    AuthorRole,
    CardCountRole,
    CoverPathRole,
    DeckFilterProxyModel,
    DeckListModel,
    DeckPathRole,
    DeckRole,
    EntryRole,
    StateRole,
    SubtitleRole,
    deck_subtitle,
    is_majors_only,
)
from tarot_canvas.ui.windows.deck_download_dialog import failure_text
from tarot_canvas.utils.package_download import DownloadFailure, FailureKind
from tests.unit.test_catalog import index, raw_entry


def fake_deck(name, author="Unknown", majors=3, minors=0, images=True, path=None, identifier=None):
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
        get_identifier=lambda: identifier,
        get_deck_id=lambda: None,
        _metadata={"deck": {"author": author}},
    )


def catalog_entry(slug, **overrides):
    (entry,) = parse_index(index(raw_entry(slug, **overrides)))
    return entry


def test_majors_only_deck_is_labelled():
    deck = fake_deck("Share The Magic", author="Lila Hunnisett", majors=22, minors=0)
    assert is_majors_only(deck)
    assert deck_subtitle(deck) == "Lila Hunnisett • majors only"
    assert deck_subtitle(deck, abbreviated=True) == "Lila Hunnisett • majors"


def test_partial_deck_gets_no_label_rather_than_a_wrong_one():
    """Majors plus one suit is not 'majors only'; a wrong label is worse than none."""
    deck = fake_deck("Partial", majors=22, minors=14)
    assert not is_majors_only(deck)
    assert deck_subtitle(deck) == "Unknown"


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
    assert model.data(index, SubtitleRole) == "P. C. Smith"
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


# -- ghosts: catalog decks not installed yet ------------------------------

AQUATIC = catalog_entry("aquatic-tarot")
ASCII = catalog_entry("ascii-tarot")


@pytest.fixture
def ghost_proxy(qapp):
    decks = [
        fake_deck("Zodiac", author="Alice", majors=22, minors=56),
        fake_deck("Aurora", author="Zeno", majors=22, minors=0),
        fake_deck("Marigold", author="Alice", majors=22, minors=14),
    ]
    model = DeckListModel(decks, entries=[ASCII, AQUATIC])
    proxy = DeckFilterProxyModel()
    proxy.setSourceModel(model)
    return proxy


def row_names(model):
    return [model.data(model.index(row, 0)) for row in range(model.rowCount())]


@pytest.mark.parametrize("key", [SORT_NAME, SORT_AUTHOR, SORT_COUNT, SORT_RECENT])
def test_ghosts_trail_installed_decks_under_every_sort(ghost_proxy, key):
    """Recently opened sorts descending, which would put ghosts first."""
    ghost_proxy.set_sort_key(key)
    order = names(ghost_proxy)
    assert sorted(order[:3]) == ["Aurora", "Marigold", "Zodiac"]
    assert order[3:] == ["Aquatic Tarot", "Ascii Tarot"]


def test_a_ghost_has_no_deck_and_no_path(qapp):
    model = DeckListModel([], entries=[AQUATIC])
    ghost = model.index(0, 0)
    assert model.data(ghost) == "Aquatic Tarot"
    assert model.data(ghost, DeckRole) is None
    assert model.data(ghost, DeckPathRole) is None
    assert model.data(ghost, EntryRole) is AQUATIC
    assert model.data(ghost, StateRole) is DeckState.AVAILABLE
    assert model.data(ghost, SubtitleRole) == QLocale().formattedDataSize(AQUATIC.package_size)
    assert model.data(ghost, AuthorRole) == "Test Artist"
    assert model.data(ghost, CardCountRole) == 78
    assert model.data(ghost, CoverPathRole) is None  # not fetched yet


def test_an_installed_deck_is_installed_and_has_no_entry(qapp):
    model = DeckListModel([fake_deck("Zodiac")], entries=[AQUATIC])
    deck = model.index(0, 0)
    assert model.data(deck, StateRole) is DeckState.INSTALLED
    assert model.data(deck, EntryRole) is None


def test_search_finds_a_ghost_by_its_artist(ghost_proxy):
    ghost_proxy.set_sort_key(SORT_NAME)
    ghost_proxy.setFilterFixedString("test artist")
    assert names(ghost_proxy) == ["Aquatic Tarot", "Ascii Tarot"]


def test_an_entry_an_installed_deck_matches_has_no_row(qapp):
    installed = fake_deck("Aquatic", identifier=AQUATIC.identifier)
    model = DeckListModel([installed], entries=[AQUATIC, ASCII])
    assert row_names(model) == ["Aquatic", "Ascii Tarot"]


def test_installing_the_matching_deck_replaces_the_ghost(qapp):
    model = DeckListModel([], entries=[AQUATIC])
    assert model.data(model.index(0, 0), DeckRole) is None

    model.set_decks([fake_deck("Aquatic", identifier=AQUATIC.identifier)])
    assert row_names(model) == ["Aquatic"]
    assert model.data(model.index(0, 0), DeckRole) is not None


def test_set_entries_replaces_the_ghosts(qapp):
    model = DeckListModel([fake_deck("Zodiac")], entries=[AQUATIC])
    model.set_entries([AQUATIC, ASCII])
    assert row_names(model) == ["Zodiac", "Aquatic Tarot", "Ascii Tarot"]
    model.set_entries([])
    assert row_names(model) == ["Zodiac"]


def test_a_download_or_cover_change_repaints_only_its_row(qapp):
    model = DeckListModel([fake_deck("Zodiac")], entries=[AQUATIC, ASCII])
    changed = []
    model.dataChanged.connect(lambda top, bottom, *_: changed.append((top.row(), bottom.row())))

    model.download_changed(ASCII.slug)
    assert changed == [(2, 2)]

    changed.clear()
    model.cover_ready(AQUATIC.cover)
    assert changed == [(1, 1)]

    changed.clear()
    model.download_changed("not-in-the-catalog")
    assert changed == []


def test_a_failed_ghost_says_why_in_its_tooltip(qapp, fake_downloads):
    model = DeckListModel([], entries=[AQUATIC])
    deck_downloads().start(AQUATIC)
    failure = DownloadFailure(FailureKind.NETWORK, "offline")
    fake_downloads[0].failed.emit(failure)

    ghost = model.index(0, 0)
    assert model.data(ghost, StateRole) is DeckState.FAILED
    assert model.data(ghost, Qt.ItemDataRole.ToolTipRole) == failure_text(failure)
