from tarot_canvas.ui.library.deck_details import DeckDetails, details_for
from tarot_canvas.ui.library.deck_downloads import DeckState, deck_downloads
from tarot_canvas.ui.library.deck_model import DeckListModel
from tarot_canvas.utils.package_download import DownloadFailure, FailureKind
from tests.unit.test_library_model import catalog_entry, fake_deck

AQUATIC = catalog_entry("aquatic-tarot")


def only_row(model):
    """The model is the caller's, so it outlives the index"""
    return details_for(model.index(0, 0))


def test_an_installed_row_reads_the_deck(qapp):
    deck = fake_deck(
        "Zodiac",
        author="Alice",
        majors=22,
        minors=56,
        version="1.2",
        license="CC0-1.0",
        attribution="By Alice",
        description="Stars",
    )
    model = DeckListModel([deck])

    assert only_row(model) == DeckDetails(
        name="Zodiac",
        artist="Alice",
        cover_path="/decks/Zodiac/major_arcana/0.png",
        card_count=78,
        version="1.2",
        license="CC0-1.0",
        attribution="By Alice",
        description="Stars",
        size=None,
        state=DeckState.INSTALLED,
        progress=None,
        failure=None,
        deck=deck,
        entry=None,
    )


def test_an_installed_deck_missing_a_field_shows_none_rather_than_a_stand_in(qapp):
    model = DeckListModel([fake_deck("Bare", author=None)])
    details = only_row(model)

    assert details.license is None
    assert details.attribution is None
    assert details.description is None
    # Not the tile's "Unknown", nor get_version()'s "Unknown Version"
    assert details.artist is None
    assert details.version is None


def test_a_ghost_row_reads_its_entry(qapp):
    model = DeckListModel([], entries=[AQUATIC])

    assert only_row(model) == DeckDetails(
        name=AQUATIC.name,
        artist=AQUATIC.artist,
        cover_path=None,
        card_count=AQUATIC.card_count,
        version=AQUATIC.version,
        license=AQUATIC.license,
        attribution=AQUATIC.attribution,
        description=AQUATIC.description,
        size=AQUATIC.package_size,
        state=DeckState.AVAILABLE,
        progress=None,
        failure=None,
        deck=None,
        entry=AQUATIC,
    )


def test_a_downloading_ghost_carries_its_progress(qapp, fake_downloads):
    model = DeckListModel([], entries=[AQUATIC])
    deck_downloads().start(AQUATIC)
    fake_downloads[0].progress.emit(40, 100)

    details = only_row(model)
    assert details.state is DeckState.DOWNLOADING
    assert details.progress == 0.4
    assert details.failure is None


def test_failure_is_set_only_for_a_failed_ghost(qapp, fake_downloads):
    model = DeckListModel([], entries=[AQUATIC])
    deck_downloads().start(AQUATIC)
    failure = DownloadFailure(FailureKind.NETWORK, "offline")
    fake_downloads[0].failed.emit(failure)

    details = only_row(model)
    assert details.state is DeckState.FAILED
    assert details.failure == failure
    assert details.progress is None


def test_a_ghost_without_attribution_shows_none(qapp):
    model = DeckListModel([], entries=[catalog_entry("aquatic-tarot", attribution=None)])
    assert only_row(model).attribution is None
