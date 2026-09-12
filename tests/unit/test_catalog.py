import json
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from tarot_canvas.models.catalog import (
    INDEX_FORMAT,
    INDEX_TTL,
    IndexAction,
    IndexMeta,
    available_entries,
    index_action,
    is_installed,
    parse_index,
    read_index,
)


def raw_entry(slug="aquatic-tarot", **overrides):
    entry = {
        "slug": slug,
        "identifier": f"land.arcana/deck/{slug}",
        "name": slug.replace("-", " ").title(),
        "artist": "Test Artist",
        "version": "2.0",
        "schema_version": "2.0",
        "license": "CC0-1.0",
        "attribution": "Test attribution",
        "description": "Test description",
        "card_count": 78,
        "cover": f"https://example.org/{slug}/h800/major_arcana/00.jpg",
        "package": {
            "url": f"https://example.org/{slug}-2.0.tarotdeck",
            "size": 1234,
            "sha256": "ab" * 32,
        },
    }
    entry.update(overrides)
    return entry


def index(*entries, **top):
    doc = {"format": INDEX_FORMAT, "source_commit": "abc1234", "decks": list(entries)}
    doc.update(top)
    return json.dumps(doc).encode()


def slugs(entries):
    return [entry.slug for entry in entries]


# --- parse_index ---------------------------------------------------------------------


def test_a_well_formed_entry_parses():
    (entry,) = parse_index(
        index(raw_entry(package={**raw_entry()["package"], "sha256": "AB" * 32}))
    )

    assert entry.slug == "aquatic-tarot"
    assert entry.identifier == "land.arcana/deck/aquatic-tarot"
    assert entry.card_count == 78
    assert entry.cover == "https://example.org/aquatic-tarot/h800/major_arcana/00.jpg"
    assert entry.package_url == "https://example.org/aquatic-tarot-2.0.tarotdeck"
    assert entry.package_size == 1234
    assert entry.package_sha256 == "ab" * 32


@pytest.mark.parametrize("fmt", [2, 0, "1", True, None], ids=repr)
def test_an_unknown_format_gives_no_entries(fmt):
    data = index(raw_entry(), format=fmt)
    assert parse_index(data) == []
    assert read_index(data) is None


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not json",
        b"\xff\xfe\x00",
        b"[]",
        b'"index"',
        b'{"format": 1}',
        b'{"format": 1, "decks": {}}',
    ],
    ids=["empty", "not-json", "binary", "array", "string", "no-decks", "decks-not-a-list"],
)
def test_not_an_index_gives_no_entries(data):
    assert parse_index(data) == []
    assert read_index(data) is None


def test_an_index_offering_nothing_is_still_an_index():
    assert read_index(index()) == []


def test_unknown_keys_are_ignored_at_both_levels():
    entry = raw_entry(sparkles=True, package={**raw_entry()["package"], "mirror": "x"})
    assert slugs(parse_index(index(entry, future={"anything": 1}))) == ["aquatic-tarot"]


@pytest.mark.parametrize("key", ["attribution", "cover"])
def test_cover_and_attribution_may_be_null_or_absent(key):
    absent = raw_entry()
    del absent[key]
    null = raw_entry(slug="ascii-tarot", **{key: None})

    entries = parse_index(index(absent, null))
    assert slugs(entries) == ["aquatic-tarot", "ascii-tarot"]
    assert all(getattr(entry, key) is None for entry in entries)


def _without(key):
    entry = raw_entry(slug="bad")
    del entry[key]
    return entry


def _package(**changes):
    return raw_entry(slug="bad", package={**raw_entry()["package"], **changes})


def _package_without(key):
    package = dict(raw_entry()["package"])
    del package[key]
    return raw_entry(slug="bad", package=package)


REQUIRED = [
    "slug",
    "identifier",
    "name",
    "artist",
    "version",
    "schema_version",
    "license",
    "description",
    "card_count",
    "package",
]

REJECTED = {
    **{f"missing-{key}": _without(key) for key in REQUIRED},
    **{f"missing-package-{key}": _package_without(key) for key in ("url", "size", "sha256")},
    "not-an-object": "bad",
    "name-not-text": raw_entry(slug="bad", name=5),
    "attribution-not-text": raw_entry(slug="bad", attribution=["x"]),
    "card-count-text": raw_entry(slug="bad", card_count="78"),
    "card-count-bool": raw_entry(slug="bad", card_count=True),
    "package-not-an-object": raw_entry(slug="bad", package="https://example.org/x"),
    "size-text": _package(size="1234"),
    "size-zero": _package(size=0),
    "size-negative": _package(size=-1),
    "slug-dotdot": raw_entry(slug=".."),
    "slug-with-slash": raw_entry(slug="a/b"),
    "slug-empty": raw_entry(slug=""),
    "package-http": _package(url="http://example.org/x.tarotdeck"),
    "package-file": _package(url="file:///tmp/x.tarotdeck"),
    "cover-http": raw_entry(slug="bad", cover="http://example.org/00.jpg"),
    "sha256-short": _package(sha256="ab" * 31),
    "sha256-not-hex": _package(sha256="zz" * 32),
    "sha256-prefixed": _package(sha256="sha256:" + "ab" * 32),
    "schema-unparseable": raw_entry(slug="bad", schema_version="x"),
    "schema-empty": raw_entry(slug="bad", schema_version=""),
}


@pytest.mark.parametrize("bad", REJECTED.values(), ids=REJECTED.keys())
def test_a_rejected_entry_is_dropped_alone(bad):
    good = raw_entry()
    other = raw_entry(slug="ascii-tarot")
    assert slugs(parse_index(index(good, bad, other))) == ["aquatic-tarot", "ascii-tarot"]


@pytest.mark.parametrize(
    ("schema_version", "kept"),
    [("1.1", True), ("2.0", True), ("2", True), ("3.0", False), ("0.9", False), ("x", False)],
)
def test_the_schema_major_gate(schema_version, kept):
    entries = parse_index(index(raw_entry(schema_version=schema_version)))
    assert slugs(entries) == (["aquatic-tarot"] if kept else [])


# --- the join --------------------------------------------------------------------


def deck(identifier=None, deck_id=None, path="/decks/unrelated", name="Unrelated"):
    return SimpleNamespace(
        get_identifier=lambda: identifier,
        get_deck_id=lambda: deck_id,
        get_name=lambda: name,
        deck_path=path,
    )


RWS, AQUATIC, ASCII = parse_index(
    index(
        raw_entry(slug="rider-waite-smith"),
        raw_entry(slug="aquatic-tarot"),
        raw_entry(slug="ascii-tarot", identifier="land.arcana/deck/ascii-tarot-lawreka"),
    )
)

JOIN = {
    "rws-1.1-by-id": (RWS, deck(deck_id="rider-waite-smith", path="/data/reference"), True),
    "ascii-by-identifier": (
        ASCII,
        deck(identifier="land.arcana/deck/ascii-tarot-lawreka", path="/decks/whatever"),
        True,
    ),
    "external-copy-by-directory": (AQUATIC, deck(path="/external/decks/aquatic-tarot"), True),
    "same-name-unrelated": (
        AQUATIC,
        deck(identifier="org.example/deck/aquatic", path="/decks/mine", name="Aquatic Tarot"),
        False,
    ),
    "same-name-no-identity": (AQUATIC, deck(path="/decks/my-aquatic", name="Aquatic Tarot"), False),
    "identifier-beats-directory": (
        AQUATIC,
        deck(identifier="org.example/deck/other", path="/decks/aquatic-tarot"),
        False,
    ),
    "id-beats-directory": (AQUATIC, deck(deck_id="other", path="/decks/aquatic-tarot"), False),
}


@pytest.mark.parametrize(("entry", "installed", "expected"), JOIN.values(), ids=JOIN.keys())
def test_is_installed(entry, installed, expected):
    assert is_installed(entry, installed) is expected


def test_available_entries_are_those_no_deck_matches():
    decks = [
        deck(deck_id="rider-waite-smith", path="/data/reference"),
        deck(identifier="land.arcana/deck/ascii-tarot-lawreka"),
        deck(path="/decks/unrelated"),
    ]
    assert slugs(available_entries([RWS, AQUATIC, ASCII], decks)) == ["aquatic-tarot"]
    assert available_entries([RWS, AQUATIC, ASCII], []) == [RWS, AQUATIC, ASCII]
    assert available_entries([], decks) == []


# --- index_action ----------------------------------------------------------------

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
SECOND = timedelta(seconds=1)


def meta(age=timedelta(0), app_version="1.4.1"):
    return IndexMeta("https://example.org/index.json", '"etag"', NOW - age, app_version)


ACTIONS = {
    "cold": (None, False, INDEX_TTL, IndexAction.FETCH),
    "cold-attempted": (None, True, INDEX_TTL, IndexAction.USE_CACHE),
    "attempted-beats-stale-and-version": (
        meta(age=INDEX_TTL * 3, app_version="1.0.0"),
        True,
        INDEX_TTL,
        IndexAction.USE_CACHE,
    ),
    "app-version-changed": (meta(app_version="1.0.0"), False, INDEX_TTL, IndexAction.REVALIDATE),
    "ttl-minus-1s": (meta(age=INDEX_TTL - SECOND), False, INDEX_TTL, IndexAction.USE_CACHE),
    "ttl-exactly": (meta(age=INDEX_TTL), False, INDEX_TTL, IndexAction.REVALIDATE),
    "ttl-plus-1s": (meta(age=INDEX_TTL + SECOND), False, INDEX_TTL, IndexAction.REVALIDATE),
    "fresh": (meta(), False, INDEX_TTL, IndexAction.USE_CACHE),
    "custom-ttl-zero": (meta(), False, timedelta(0), IndexAction.REVALIDATE),
    "custom-ttl-inside": (
        meta(age=timedelta(minutes=59)),
        False,
        timedelta(hours=1),
        IndexAction.USE_CACHE,
    ),
    "custom-ttl-outside": (
        meta(age=timedelta(hours=2)),
        False,
        timedelta(hours=1),
        IndexAction.REVALIDATE,
    ),
}


@pytest.mark.parametrize(
    ("meta_", "attempted", "ttl", "expected"), ACTIONS.values(), ids=ACTIONS.keys()
)
def test_index_action(meta_, attempted, ttl, expected):
    assert index_action(meta_, NOW, "1.4.1", attempted, ttl=ttl) is expected


def test_the_default_ttl_is_a_day():
    assert index_action(meta(age=timedelta(hours=23)), NOW, "1.4.1", False) is IndexAction.USE_CACHE
    assert (
        index_action(meta(age=timedelta(hours=24)), NOW, "1.4.1", False) is IndexAction.REVALIDATE
    )


# --- IndexMeta -------------------------------------------------------------------


@pytest.mark.parametrize("etag", ['"abc"', None])
def test_index_meta_round_trips(etag):
    original = IndexMeta("https://example.org/index.json", etag, NOW, "1.4.1")
    assert IndexMeta.from_dict(json.loads(json.dumps(original.to_dict()))) == original


def test_index_meta_normalises_to_utc():
    local = NOW.astimezone(timezone(timedelta(hours=-7)))
    restored = IndexMeta.from_dict(IndexMeta("u", None, local, "v").to_dict())
    assert restored.checked_at == NOW
    assert restored.checked_at.utcoffset() == timedelta(0)


GOOD_META = IndexMeta("https://example.org/index.json", '"e"', NOW, "1.4.1").to_dict()

MALFORMED_META = {
    "none": None,
    "list": [],
    "empty": {},
    "no-url": {k: v for k, v in GOOD_META.items() if k != "url"},
    "url-not-text": {**GOOD_META, "url": 5},
    "etag-not-text": {**GOOD_META, "etag": 5},
    "no-app-version": {k: v for k, v in GOOD_META.items() if k != "app_version"},
    "checked-at-garbage": {**GOOD_META, "checked_at": "yesterday"},
    "checked-at-naive": {**GOOD_META, "checked_at": "2026-09-12T12:00:00"},
    "checked-at-number": {**GOOD_META, "checked_at": 1789237295},
}


@pytest.mark.parametrize("data", MALFORMED_META.values(), ids=MALFORMED_META.keys())
def test_malformed_index_meta_is_none(data):
    assert IndexMeta.from_dict(data) is None
