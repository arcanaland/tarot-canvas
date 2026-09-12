"""The reference-deck index: what it offers, and when to ask it again.

No Qt and no I/O; ui/library/catalog_client.py does the fetching and caching.
"""

import enum
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from tarot_canvas.models.deck_install import install_dir_name

INDEX_URL = "https://raw.githubusercontent.com/arcanaland/reference-decks/main/index.json"
INDEX_FORMAT = 1
SUPPORTED_SCHEMA_MAJORS = frozenset({1, 2})
INDEX_TTL = timedelta(hours=24)

log = logging.getLogger("TarotCanvas.catalog")

_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
_REQUIRED_TEXT = (
    "slug",
    "identifier",
    "name",
    "artist",
    "version",
    "schema_version",
    "license",
    "description",
)


@dataclass(frozen=True)
class CatalogEntry:
    slug: str
    identifier: str
    name: str
    artist: str
    version: str
    schema_version: str
    license: str
    attribution: str | None
    description: str
    card_count: int
    cover: str | None
    package_url: str
    package_size: int
    package_sha256: str


class _Rejected(ValueError):
    pass


class _Unsupported(_Rejected):
    """A well-formed entry this app can't load; hidden rather than offered."""


def parse_index(data):
    """The entries of an index document, or [] if it isn't one this app reads."""
    return read_index(data) or []


def read_index(data):
    """Like parse_index, but None when the document itself is unreadable.

    An empty list is an index that offers nothing, which is not the same as an index
    from a newer format.
    """
    try:
        doc = json.loads(data)
    except (ValueError, RecursionError):
        log.warning("index is not JSON; offering no decks")
        return None
    if not isinstance(doc, dict):
        log.warning("index is not a JSON object; offering no decks")
        return None
    fmt = doc.get("format")
    # bool is an int, and True == 1
    if type(fmt) is not int or fmt != INDEX_FORMAT:
        log.warning("index format %r is not %d; offering no decks", fmt, INDEX_FORMAT)
        return None
    decks = doc.get("decks")
    if not isinstance(decks, list):
        log.warning("index has no list of decks; offering no decks")
        return None

    entries = []
    for raw in decks:
        try:
            entries.append(_entry(raw))
        except _Unsupported as e:
            log.info("index entry %s hidden: %s", _label(raw), e)
        except _Rejected as e:
            log.warning("index entry %s dropped: %s", _label(raw), e)
    return entries


def _entry(raw):
    if not isinstance(raw, dict):
        raise _Rejected("not an object")
    for key in _REQUIRED_TEXT:
        _require(raw, key, str)
    attribution = _optional(raw, "attribution", str)
    cover = _optional(raw, "cover", str)
    card_count = _require(raw, "card_count", int)
    package = _require(raw, "package", dict)
    url = _require(package, "url", str)
    size = _require(package, "size", int)
    sha256 = _require(package, "sha256", str)

    try:
        install_dir_name(None, raw["slug"])
    except ValueError as e:
        raise _Rejected(f"slug: {e}") from e
    if not _is_https(url):
        raise _Rejected(f"package url is not https: {url!r}")
    if cover is not None and not _is_https(cover):
        raise _Rejected(f"cover is not https: {cover!r}")
    if not _SHA256.fullmatch(sha256):
        raise _Rejected(f"sha256 is not 64 hex characters: {sha256!r}")
    if size <= 0:
        raise _Rejected(f"package size is {size}")

    schema_version = raw["schema_version"]
    try:
        major = int(schema_version.split(".")[0])
    except ValueError as e:
        raise _Rejected(f"schema_version {schema_version!r}") from e
    if major not in SUPPORTED_SCHEMA_MAJORS:
        raise _Unsupported(f"schema_version {schema_version}")

    return CatalogEntry(
        slug=raw["slug"],
        identifier=raw["identifier"],
        name=raw["name"],
        artist=raw["artist"],
        version=raw["version"],
        schema_version=schema_version,
        license=raw["license"],
        attribution=attribution,
        description=raw["description"],
        card_count=card_count,
        cover=cover,
        package_url=url,
        package_size=size,
        package_sha256=sha256.lower(),
    )


def _require(obj, key, kind):
    if key not in obj:
        raise _Rejected(f"missing {key!r}")
    value = obj[key]
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise _Rejected(f"{key!r} is not {kind.__name__}")
    return value


def _optional(obj, key, kind):
    if obj.get(key) is None:
        return None
    return _require(obj, key, kind)


def _is_https(url):
    parts = urlsplit(url)
    return parts.scheme == "https" and bool(parts.netloc)


def _label(raw):
    return repr(raw.get("slug")) if isinstance(raw, dict) else repr(raw)[:40]


def is_installed(entry, deck):
    """Whether a loaded deck is this entry.

    A deck with a spec identifier joins on it. Older copies, which predate identifiers,
    join on their 1.x id or else their directory name against the slug.
    """
    identifier = deck.get_identifier()
    if identifier:
        return identifier == entry.identifier
    return (deck.get_deck_id() or Path(deck.deck_path).name) == entry.slug


def available_entries(entries, decks):
    """The entries no loaded deck matches."""
    decks = list(decks)
    return [entry for entry in entries if not any(is_installed(entry, d) for d in decks)]


@dataclass(frozen=True)
class IndexMeta:
    url: str
    etag: str | None
    checked_at: datetime
    app_version: str

    def to_dict(self):
        return {
            "url": self.url,
            "etag": self.etag,
            "checked_at": self.checked_at.astimezone(UTC).isoformat(),
            "app_version": self.app_version,
        }

    @classmethod
    def from_dict(cls, data):
        """The meta, or None if `data` isn't one."""
        if not isinstance(data, dict):
            return None
        url, etag, checked_at, app_version = (
            data.get(key) for key in ("url", "etag", "checked_at", "app_version")
        )
        if not all(isinstance(value, str) for value in (url, checked_at, app_version)):
            return None
        if etag is not None and not isinstance(etag, str):
            return None
        try:
            when = datetime.fromisoformat(checked_at)
        except ValueError:
            return None
        if when.tzinfo is None:
            return None
        return cls(url, etag, when.astimezone(UTC), app_version)


class IndexAction(enum.Enum):
    FETCH = "fetch"
    REVALIDATE = "revalidate"
    USE_CACHE = "use cache"


def index_action(meta, now, app_version, attempted_this_session, ttl=INDEX_TTL):
    """What to do about the cached index.

    Everything the index points at is immutable, so a stale index is late, never wrong.
    """
    if attempted_this_session:
        return IndexAction.USE_CACHE  # one try per session, success or not
    if meta is None:
        return IndexAction.FETCH  # cold: nothing to show yet
    if meta.app_version != app_version:
        return IndexAction.REVALIDATE  # a new app may accept what the old one hid
    if now - meta.checked_at >= ttl:
        return IndexAction.REVALIDATE
    return IndexAction.USE_CACHE
