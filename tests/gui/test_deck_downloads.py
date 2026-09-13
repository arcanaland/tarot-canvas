import pytest

from tarot_canvas.ui.library.deck_downloads import DeckState, deck_downloads
from tarot_canvas.utils.package_download import DownloadFailure, FailureKind
from tarot_canvas.utils.path_helper import get_decks_directory, get_staging_directory
from tests.unit.test_library_model import catalog_entry

ENTRY = catalog_entry("aquatic-tarot")
SLUG = ENTRY.slug


@pytest.fixture
def downloads(qapp, fake_downloads):
    downloads = deck_downloads()
    downloads.seen = []
    downloads.changed.connect(downloads.seen.append)
    return downloads


def test_start_makes_one_download_into_the_primary_deck_root(downloads, fake_downloads):
    downloads.start(ENTRY)

    (job,) = fake_downloads
    assert job.started
    assert job.dest == get_decks_directory()[0] / "aquatic-tarot"
    assert job.staging_root == get_staging_directory()
    assert (job.url, job.size, job.sha256) == (
        ENTRY.package_url,
        ENTRY.package_size,
        ENTRY.package_sha256,
    )
    assert downloads.state(SLUG) is DeckState.DOWNLOADING
    assert downloads.progress(SLUG) == 0.0
    assert downloads.seen == [SLUG]


def test_a_second_start_for_a_running_download_does_nothing(downloads, fake_downloads):
    downloads.start(ENTRY)
    downloads.start(ENTRY)
    assert len(fake_downloads) == 1


def test_progress_is_a_fraction_and_repaints_only_per_percent(downloads, fake_downloads):
    downloads.start(ENTRY)
    job = fake_downloads[0]

    job.progress.emit(40, 100)
    assert downloads.progress(SLUG) == pytest.approx(0.4)
    assert downloads.seen == [SLUG, SLUG]

    job.progress.emit(405, 1000)
    assert downloads.seen == [SLUG, SLUG]


def test_a_failure_is_kept_until_the_next_start(downloads, fake_downloads):
    downloads.start(ENTRY)
    fake_downloads[0].failed.emit(DownloadFailure(FailureKind.NETWORK, "offline"))

    assert downloads.state(SLUG) is DeckState.FAILED
    assert downloads.failure(SLUG).kind is FailureKind.NETWORK
    assert downloads.progress(SLUG) is None

    downloads.start(ENTRY)
    assert len(fake_downloads) == 2
    assert downloads.state(SLUG) is DeckState.DOWNLOADING
    assert downloads.failure(SLUG) is None


def test_cancelling_returns_to_available_not_failed(downloads, fake_downloads):
    downloads.start(ENTRY)
    downloads.cancel(SLUG)

    assert fake_downloads[0].cancelled
    assert downloads.state(SLUG) is DeckState.AVAILABLE
    assert downloads.failure(SLUG) is None


def test_success_rescans_then_announces_the_deck(downloads, fake_downloads, stub_deck_manager):
    events = []
    stub_deck_manager.rescan = lambda: events.append("rescan")
    downloads.installed.connect(lambda entry: events.append(entry))

    downloads.start(ENTRY)
    fake_downloads[0].succeeded.emit(str(fake_downloads[0].dest))

    assert events == ["rescan", ENTRY]
    assert downloads.state(SLUG) is DeckState.AVAILABLE  # the join hides it from here on
    assert downloads.progress(SLUG) is None


def test_an_identifier_that_is_no_directory_name_fails_without_downloading(
    downloads, fake_downloads
):
    entry = catalog_entry("aquatic-tarot", identifier="land.arcana/deck/")
    downloads.start(entry)

    assert fake_downloads == []
    assert downloads.state(SLUG) is DeckState.FAILED
    assert downloads.failure(SLUG).kind is FailureKind.FILESYSTEM


def test_downloads_are_app_wide(downloads, fake_downloads):
    downloads.start(ENTRY)
    assert deck_downloads() is downloads
    assert deck_downloads().state(SLUG) is DeckState.DOWNLOADING


def test_a_real_download_is_out_of_reach_in_tests(qapp):
    with pytest.raises(AssertionError, match="fake_downloads"):
        deck_downloads().start(ENTRY)
