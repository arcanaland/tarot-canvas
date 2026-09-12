import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tarot_canvas._version import __version__
from tarot_canvas.models.catalog import INDEX_URL, IndexMeta, parse_index
from tarot_canvas.settings import SHOW_AVAILABLE_DECKS_KEY, get_settings
from tarot_canvas.ui.library import catalog_client
from tarot_canvas.ui.library.catalog_client import DeckCatalog, deck_catalog
from tests.unit.test_catalog import index, raw_entry, slugs

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
STALE = timedelta(hours=25)
FRESH = timedelta(hours=1)

INDEX = index(raw_entry())
NEWER = index(raw_entry(), raw_entry(slug="ascii-tarot"))
COVER_URL = raw_entry()["cover"]
COVER_NAME = hashlib.sha256(COVER_URL.encode()).hexdigest()[:32] + ".jpg"


class FakeTransport:
    """Records requests and answers them only when a test says so."""

    def __init__(self):
        self.requests = []
        self._pending = {}

    def get(self, url, *, etag=None, callback):
        self.requests.append((url, etag))
        self._pending.setdefault(url, []).append(callback)

    def reply(self, url, status=200, body=b"", etag=None, error=None):
        self._pending[url].pop(0)(status, body, etag, error)

    def index_requests(self, url=INDEX_URL):
        return [request for request in self.requests if request[0] == url]


@pytest.fixture(autouse=True)
def no_overrides(monkeypatch):
    monkeypatch.delenv(catalog_client.URL_ENV, raising=False)
    monkeypatch.delenv(catalog_client.TTL_ENV, raising=False)


@pytest.fixture(autouse=True)
def switch_unset(qapp):
    """QSettings is shared across the process, so a test that turns the switch off leaks."""
    get_settings().remove(SHOW_AVAILABLE_DECKS_KEY)
    yield
    get_settings().remove(SHOW_AVAILABLE_DECKS_KEY)


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "catalog"


@pytest.fixture
def make(qapp, transport, cache):
    def make():
        catalog = DeckCatalog(transport=transport, cache_dir=cache, clock=lambda: NOW)
        catalog.emitted = []
        catalog.entries_changed.connect(lambda: catalog.emitted.append(slugs(catalog.entries())))
        return catalog

    return make


def seed(cache, body=INDEX, age=FRESH, etag='"v1"', app_version=__version__, url=INDEX_URL):
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "index.json").write_bytes(body)
    meta = IndexMeta(url, etag, NOW - age, app_version)
    (cache / "index.meta.json").write_text(json.dumps(meta.to_dict()))


def seed_cover(cache, name=COVER_NAME, data=b"jpeg"):
    (cache / "covers").mkdir(parents=True, exist_ok=True)
    (cache / "covers" / name).write_bytes(data)
    return cache / "covers" / name


def read_meta(cache):
    return IndexMeta.from_dict(json.loads((cache / "index.meta.json").read_text()))


# --- the index ---------------------------------------------------------------------


def test_cold_start_sends_one_unconditional_get_writes_the_cache_and_emits(make, transport, cache):
    catalog = make()
    catalog.activate()

    assert transport.index_requests() == [(INDEX_URL, None)]
    assert catalog.entries() == []
    assert catalog.emitted == []

    transport.reply(INDEX_URL, 200, INDEX, etag='"v1"')

    assert catalog.emitted == [["aquatic-tarot"]]
    assert (cache / "index.json").read_bytes() == INDEX
    assert read_meta(cache) == IndexMeta(INDEX_URL, '"v1"', NOW, __version__)


def test_a_warm_cache_renders_from_the_cache_and_sends_nothing(make, transport, cache):
    seed(cache)
    seed_cover(cache)
    catalog = make()
    catalog.activate()

    assert catalog.emitted == [["aquatic-tarot"]]
    assert transport.requests == []


def test_a_stale_cache_renders_then_sends_one_conditional_get(make, transport, cache):
    seed(cache, age=STALE)
    seed_cover(cache)
    catalog = make()
    catalog.activate()

    assert catalog.emitted == [["aquatic-tarot"]]
    assert transport.requests == [(INDEX_URL, '"v1"')]


def test_304_bumps_checked_at_and_leaves_the_index_alone(make, transport, cache):
    seed(cache, age=STALE)
    catalog = make()
    catalog.activate()
    transport.reply(INDEX_URL, 304)

    assert (cache / "index.json").read_bytes() == INDEX
    assert read_meta(cache) == IndexMeta(INDEX_URL, '"v1"', NOW, __version__)
    assert catalog.emitted == [["aquatic-tarot"]]


def test_200_replaces_the_index_atomically(make, transport, cache):
    seed(cache, age=STALE)
    (cache / "index.json.tmp").write_bytes(b"left by a crash")
    catalog = make()
    catalog.activate()
    transport.reply(INDEX_URL, 200, NEWER, etag='"v2"')

    assert (cache / "index.json").read_bytes() == NEWER
    assert not (cache / "index.json.tmp").exists()
    assert not (cache / "index.meta.json.tmp").exists()
    assert read_meta(cache).etag == '"v2"'
    assert catalog.emitted == [["aquatic-tarot"], ["aquatic-tarot", "ascii-tarot"]]


def test_200_with_the_same_entries_does_not_re_emit(make, transport, cache):
    seed(cache, age=STALE)
    catalog = make()
    catalog.activate()
    transport.reply(INDEX_URL, 200, index(raw_entry(), source_commit="other"), etag='"v2"')

    assert catalog.emitted == [["aquatic-tarot"]]
    assert read_meta(cache).etag == '"v2"'


def test_200_in_an_unknown_format_is_stored_and_offers_nothing(make, transport, cache):
    seed(cache, age=STALE)
    future = index(raw_entry(), format=2)
    catalog = make()
    catalog.activate()
    transport.reply(INDEX_URL, 200, future, etag='"v2"')

    assert (cache / "index.json").read_bytes() == future
    assert catalog.entries() == []
    assert catalog.emitted == [["aquatic-tarot"], []]


@pytest.mark.parametrize(
    ("status", "error"),
    [(None, "HostNotFoundError: no such host"), (500, "InternalServerError: oops"), (403, None)],
    ids=["network", "http-500", "http-403-no-error"],
)
def test_an_error_keeps_the_cache_and_is_not_retried_this_session(
    make, transport, cache, status, error
):
    seed(cache, age=STALE)
    catalog = make()
    catalog.activate()
    transport.reply(INDEX_URL, status, b"error page", error=error)

    assert (cache / "index.json").read_bytes() == INDEX
    assert read_meta(cache).checked_at == NOW - STALE
    assert slugs(catalog.entries()) == ["aquatic-tarot"]

    catalog.activate()
    catalog.set_enabled(False)
    catalog.set_enabled(True)
    assert len(transport.index_requests()) == 1


def test_a_failed_cold_fetch_is_not_retried_by_re_enabling(make, transport, cache):
    catalog = make()
    catalog.activate()
    transport.reply(INDEX_URL, None, error="HostNotFoundError: no such host")

    catalog.set_enabled(False)
    catalog.set_enabled(True)
    assert len(transport.index_requests()) == 1


def test_closing_and_reopening_the_library_sends_one_request(make, transport, cache):
    catalog = make()
    catalog.activate()
    catalog.activate()  # before the reply
    transport.reply(INDEX_URL, 200, INDEX, etag='"v1"')
    catalog.activate()  # after it

    assert len(transport.index_requests()) == 1
    assert catalog.emitted == [["aquatic-tarot"]]


def test_a_changed_app_version_revalidates_inside_the_ttl(make, transport, cache):
    seed(cache, age=FRESH, app_version="0.0.1")
    catalog = make()
    catalog.activate()
    assert transport.index_requests() == [(INDEX_URL, '"v1"')]

    transport.reply(INDEX_URL, 304)
    assert read_meta(cache).app_version == __version__


def test_an_overridden_url_ignores_the_default_urls_cache(make, transport, cache, monkeypatch):
    branch = "https://example.org/branch/index.json"
    monkeypatch.setenv(catalog_client.URL_ENV, branch)
    seed(cache, age=FRESH, url=INDEX_URL)
    catalog = make()
    catalog.activate()

    assert transport.index_requests(branch) == [(branch, None)]
    assert transport.index_requests(INDEX_URL) == []
    assert catalog.emitted == []

    transport.reply(branch, 200, NEWER, etag='"b1"')
    assert read_meta(cache).url == branch


def test_a_meta_without_its_index_is_cold(make, transport, cache):
    seed(cache, age=FRESH)
    (cache / "index.json").unlink()
    make().activate()

    assert transport.index_requests() == [(INDEX_URL, None)]


def test_ttl_zero_revalidates_every_session(make, transport, cache, monkeypatch):
    monkeypatch.setenv(catalog_client.TTL_ENV, "0")
    seed(cache, age=timedelta(0))
    for _session in range(2):
        make().activate()
        transport.reply(INDEX_URL, 304)

    assert transport.index_requests() == [(INDEX_URL, '"v1"')] * 2


@pytest.mark.parametrize("value", ["soon", "", "-5", "1.5"])
def test_an_unparseable_ttl_is_ignored(make, transport, cache, monkeypatch, value):
    monkeypatch.setenv(catalog_client.TTL_ENV, value)
    seed(cache, age=FRESH)
    seed_cover(cache)
    make().activate()

    assert transport.requests == []


# --- covers ------------------------------------------------------------------------


def test_covers_are_fetched_once_and_written_atomically(make, transport, cache):
    catalog = make()
    ready = []
    catalog.cover_ready.connect(ready.append)
    catalog.activate()
    transport.reply(INDEX_URL, 200, INDEX, etag='"v1"')
    (entry,) = catalog.entries()

    assert transport.index_requests(COVER_URL) == [(COVER_URL, None)]
    assert catalog.cover_path(entry) is None

    transport.reply(COVER_URL, 200, b"jpeg bytes")

    assert ready == [COVER_URL]
    assert catalog.cover_path(entry) == str(cache / "covers" / COVER_NAME)
    assert Path(catalog.cover_path(entry)).read_bytes() == b"jpeg bytes"
    assert [p.name for p in (cache / "covers").iterdir()] == [COVER_NAME]

    catalog.set_enabled(False)
    catalog.set_enabled(True)
    assert len(transport.index_requests(COVER_URL)) == 1


def test_a_failed_cover_is_not_retried_this_session(make, transport, cache):
    seed(cache)
    catalog = make()
    catalog.activate()
    transport.reply(COVER_URL, 404, b"not found", error="ContentNotFoundError: gone")

    assert catalog.cover_path(catalog.entries()[0]) is None
    catalog.set_enabled(False)
    catalog.set_enabled(True)
    assert len(transport.index_requests(COVER_URL)) == 1


@pytest.mark.parametrize("cover", ["https://example.org/00.gif", "https://example.org/00"])
def test_a_cover_of_an_unknown_type_is_skipped(make, transport, cache, cover):
    seed(cache, body=index(raw_entry(cover=cover)))
    catalog = make()
    catalog.activate()

    assert transport.requests == []
    assert catalog.cover_path(catalog.entries()[0]) is None


@pytest.mark.parametrize(
    ("outcome", "collected"),
    [
        ((200, INDEX, '"v2"', None), True),
        ((304, b"", None, None), False),
        ((None, b"", None, "HostNotFoundError: no such host"), False),
        ((200, index(raw_entry(), format=2), '"v2"', None), False),
    ],
    ids=["200", "304", "error", "200-unknown-format"],
)
def test_orphaned_covers_are_collected_only_after_a_readable_200(
    make, transport, cache, outcome, collected
):
    seed(cache, age=STALE)
    kept = seed_cover(cache)
    orphan = seed_cover(cache, name="0" * 32 + ".jpg")
    make().activate()
    transport.reply(INDEX_URL, *outcome)

    assert kept.exists()
    assert orphan.exists() is not collected


# --- the switch --------------------------------------------------------------------


def test_disabled_at_first_activate_sends_nothing_and_keeps_the_cache(make, transport, cache):
    get_settings().setValue(SHOW_AVAILABLE_DECKS_KEY, False)
    seed(cache, age=STALE)
    catalog = make()
    catalog.activate()

    assert not catalog.is_enabled()
    assert catalog.entries() == []
    assert catalog.emitted == []
    assert transport.requests == []
    assert (cache / "index.json").read_bytes() == INDEX


def test_enabling_after_a_disabled_activate_behaves_as_a_first_activate(make, transport, cache):
    get_settings().setValue(SHOW_AVAILABLE_DECKS_KEY, False)
    seed(cache, age=STALE)
    catalog = make()
    catalog.activate()
    catalog.set_enabled(True)

    assert catalog.emitted == [["aquatic-tarot"]]
    assert transport.index_requests() == [(INDEX_URL, '"v1"')]


def test_disabling_empties_the_entries_and_keeps_the_files(make, transport, cache):
    seed(cache)
    cover = seed_cover(cache)
    catalog = make()
    catalog.activate()
    catalog.set_enabled(False)

    assert catalog.entries() == []
    assert catalog.emitted == [["aquatic-tarot"], []]
    assert transport.requests == []
    assert (cache / "index.json").exists()
    assert cover.exists()


def test_set_enabled_before_activate_touches_nothing(make, transport, cache):
    seed(cache, age=STALE)
    catalog = make()
    catalog.set_enabled(False)
    catalog.set_enabled(True)

    assert transport.requests == []
    assert catalog.emitted == []


def test_the_switch_defaults_to_on(make):
    assert make().is_enabled()


# --- the singleton and import hygiene ---------------------------------------------


def test_deck_catalog_is_one_lazy_instance(qapp):
    assert catalog_client._instance is None
    first = deck_catalog()
    assert deck_catalog() is first


def test_importing_creates_no_object_file_or_request(tmp_path):
    code = "\n".join(
        [
            "from PyQt6.QtCore import QCoreApplication",
            "from tarot_canvas.models import catalog",
            "from tarot_canvas.ui.library import catalog_client",
            "assert catalog_client._instance is None",
            "assert QCoreApplication.instance() is None",
        ]
    )
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CACHE_HOME": str(home / "cache"),
        "XDG_DATA_HOME": str(home / "data"),
        "XDG_CONFIG_HOME": str(home / "config"),
    }
    repo = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, "-c", code], env=env, cwd=repo, check=True)

    assert list(home.iterdir()) == []


def test_the_parsed_fixture_is_what_the_client_serves(make, transport, cache):
    seed(cache)
    catalog = make()
    catalog.activate()
    assert catalog.entries() == parse_index(INDEX)
