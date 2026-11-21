"""Create a deck in the Library and fill it a card at a time

Decks we create store images in source/
"""

import contextlib
import enum
import logging
import os
import re
import secrets
import shutil
import tempfile
import unicodedata
from collections.abc import Mapping
from pathlib import Path

import tomlkit
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PyQt6.QtGui import QImageIOHandler, QImageReader, QImageWriter

from tarot_canvas.models import library_curation
from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS
from tarot_canvas.models.deck_container import DECK_TOML
from tarot_canvas.models.deck_install import install_dir_name
from tarot_canvas.models.toml_files import write_atomically
from tarot_canvas.utils.path_helper import get_decks_directory

log = logging.getLogger(__name__)

HEIGHT_CAP = 2400
BACK = "card_backs.classic"

IDENTIFIER_PREFIX = "land.arcana.private/deck/"
SCHEMA_VERSION = "2.0"
FIRST_VERSION = "0.1.0"
SLUG_LENGTH = 40

SOURCE = "source"
UNSORTED = "unsorted"
SETTABLE_FIELDS = ("name", "version", "artist", "description")

JPEG_QUALITY = 95
# Qt's WebP plugin writes lossless at 100
WEBP_QUALITY = 100

# Qt's format name -> the extension a derived image gets.
_BASELINE = {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}
_QUALITY = {"jpeg": JPEG_QUALITY, "webp": WEBP_QUALITY}
_VECTOR = {"svg", "svgz", "pdf"}

_ROOT = re.compile(r"h([1-9][0-9]*)")
_PARTIAL = re.compile(r"\.h[1-9][0-9]*\.partial")
_MINORS = tuple(card_id for card_id in CANONICAL_CARD_IDS if card_id.startswith("minor_arcana."))
_SLOTS = (*CANONICAL_CARD_IDS, BACK)


class DeckWriteReason(enum.Enum):
    UNREADABLE_IMAGE = "not an image that can be read"
    NOT_IN_DECK = "the card is excluded from this deck"
    UNKNOWN_CARD = "not a card ID"
    NOT_CREATED_HERE = "not a deck this app created"
    REQUIRED_FIELD = "a required field is blank"


class DeckWriteError(Exception):
    def __init__(self, reason, detail=""):
        super().__init__(f"{reason.value}: {detail}" if detail else reason.value)
        self.reason = reason
        self.detail = detail


def image_suffixes():
    """Suffixes of the images place accepts"""
    return {
        "." + name
        for name in (bytes(raw).decode().lower() for raw in QImageReader.supportedImageFormats())
        if name not in _VECTOR
    }


# -- creating ------------------------------------------------------------------------------


def slug(name):
    """name as lowercase ASCII letters, digits and single hyphens, at most SLUG_LENGTH long"""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    hyphenated = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return hyphenated[:SLUG_LENGTH].strip("-")


def mint_identifier(name):
    """A new identifier in our private realm with a random suffix"""
    hex_part = secrets.token_hex(4)
    named = slug(name)
    return f"{IDENTIFIER_PREFIX}{named}-{hex_part}" if named else f"{IDENTIFIER_PREFIX}{hex_part}"


def create(name, majors_only=True, decks_root=None):
    """Create an empty deck in decks_root, majors only unless told otherwise"""
    if not name or not name.strip():
        raise DeckWriteError(DeckWriteReason.REQUIRED_FIELD, "name")
    decks_root = Path(decks_root if decks_root is not None else get_decks_directory()[0])
    decks_root.mkdir(parents=True, exist_ok=True)
    while True:
        identifier = mint_identifier(name)
        deck = decks_root / install_dir_name(identifier, None)
        try:
            deck.mkdir()
        except FileExistsError:
            continue
        break
    try:
        write_atomically(deck / DECK_TOML, _new_manifest(name, identifier, majors_only))
    except BaseException:
        shutil.rmtree(deck, ignore_errors=True)
        raise
    library_curation.add_created_deck(deck)
    return deck


def _new_manifest(name, identifier, majors_only):
    document = tomlkit.document()
    table = tomlkit.table()
    table["schema_version"] = SCHEMA_VERSION
    table["name"] = name
    table["version"] = FIRST_VERSION
    table["identifier"] = identifier
    document["deck"] = table
    if majors_only:
        cards = tomlkit.array()
        cards.extend(_MINORS)
        cards.multiline(True)
        excluded = tomlkit.table()
        excluded["cards"] = cards
        document["excluded_cards"] = excluded
    return tomlkit.dumps(document)


def include_minors(deck):
    """Take the 56 minors out of [excluded_cards], dropping the table once it is empty"""
    deck = _checked(deck)
    manifest = deck / DECK_TOML
    document = tomlkit.parse(manifest.read_text(encoding="utf-8"))
    excluded = document.get("excluded_cards")
    if excluded is None:
        return
    minors = set(_MINORS)
    kept = [card for card in excluded.get("cards", ()) if card not in minors]
    if kept or len(excluded) > 1:
        cards = tomlkit.array()
        cards.extend(kept)
        cards.multiline(True)
        excluded["cards"] = cards
    else:
        del document["excluded_cards"]
    write_atomically(manifest, tomlkit.dumps(document))


def exclude_minors(deck, progress=None):
    """Put the 56 minors in [excluded_cards]; their originals go to unsorted/"""
    deck = _checked(deck)
    for card_id in _MINORS:
        for derived in _roots(deck):
            _clear_stem(derived / _subpath(card_id))
        for old in _originals(deck, card_id):
            _to_unsorted(deck, old)
    _remove_empty_folders(deck / SOURCE / "minor_arcana")
    for derived in _roots(deck):
        _remove_empty_folders(derived / "minor_arcana")
    manifest = deck / DECK_TOML
    document = tomlkit.parse(manifest.read_text(encoding="utf-8"))
    excluded = document.get("excluded_cards")
    if excluded is None:
        excluded = tomlkit.table()
        document["excluded_cards"] = excluded
    listed = list(excluded.get("cards", ()))
    cards = tomlkit.array()
    cards.extend([*listed, *(card for card in _MINORS if card not in listed)])
    cards.multiline(True)
    excluded["cards"] = cards
    write_atomically(manifest, tomlkit.dumps(document))
    _sync(deck, progress)


def _remove_empty_folders(top):
    """top and the folders under it, where empty"""
    if not top.is_dir():
        return
    for directory, _, _ in sorted(os.walk(top), key=lambda walked: -len(walked[0])):
        with contextlib.suppress(OSError):  # not empty
            os.rmdir(directory)


# -- [deck] fields -------------------------------------------------------------------------


def set_fields(deck, **fields):
    """Set or remove name, version, artist and description in [deck]"""
    deck = _checked(deck)
    unknown = set(fields) - set(SETTABLE_FIELDS)
    if unknown:
        raise TypeError(f"not a settable field: {', '.join(sorted(unknown))}")
    name = fields.get("name", ...)
    if name is not ... and (not name or not name.strip()):
        raise DeckWriteError(DeckWriteReason.REQUIRED_FIELD, "name")
    manifest = deck / DECK_TOML
    document = tomlkit.parse(manifest.read_text(encoding="utf-8"))
    table = document["deck"]
    for key, value in fields.items():
        if value is None or value == "":
            table.pop(key, None)
        elif isinstance(value, str):
            table[key] = value
        else:
            raise TypeError(f"{key} must be a string, not {type(value).__name__}")
    write_atomically(manifest, tomlkit.dumps(document))


# -- placing and removing cards ------------------------------------------------------------


def place(deck, card_id, image, progress=None):
    """Put image in card_id's slot"""
    deck = _checked(deck)
    _check_slot(deck, card_id)
    image = Path(image)
    _read_header(image)
    for derived in _roots(deck):
        _clear_stem(derived / _subpath(card_id))
    for old in _originals(deck, card_id):
        _to_unsorted(deck, old)
    # Under its own name, so taking it out gives that name back
    name = image.name if image.suffix else image.name + _source_suffix(image)
    target = _slot_folder(deck, card_id) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if _is_unsorted(deck, image):
        os.replace(image, target)
    else:
        with _atomic(target) as temporary:
            shutil.copyfile(image, temporary)
    _sync(deck, progress)
    if not any(_files_with_stem(root / _subpath(card_id)) for root in _roots(deck)):
        # Its header read but Qt would not decode it, so it can't stay in the slot
        _to_unsorted(deck, target)
        _sync(deck, progress)
        raise DeckWriteError(DeckWriteReason.UNREADABLE_IMAGE, os.fspath(image))


def unplace(deck, card_id, progress=None):
    """Remove card from a slot and move it to unsorted/"""
    deck = _checked(deck)
    _check_card_id(card_id)
    for derived in _roots(deck):
        _clear_stem(derived / _subpath(card_id))
    for old in _originals(deck, card_id):
        _to_unsorted(deck, old)
    with contextlib.suppress(OSError):  # gone already, or not empty
        _slot_folder(deck, card_id).rmdir()
    _sync(deck, progress)


def place_many(deck, placements, unsorted, progress=None):
    """Place {card_id: image} shortest first, then copy each of unsorted into unsorted/

    Carries on past a file that fails, which goes to unsorted/ if it can; returns the failed
    files' paths.
    """
    deck = _checked(deck)
    total = len(placements) + len(unsorted)
    done = 0
    failed = []

    def advance():
        nonlocal done
        done += 1
        if progress is not None:
            progress(done, total)

    if progress is not None and total:
        progress(0, total)
    heights = {}
    for card_id, image in placements.items():
        try:
            heights[card_id] = oriented_height(image)
        except DeckWriteError:
            failed.append(os.fspath(image))
            advance()
    # The first placed fixes H, so no later one regenerates the rest
    for card_id in sorted(heights, key=heights.get):
        image = placements[card_id]
        try:
            place(deck, card_id, image)
        except DeckWriteError as error:
            failed.append(os.fspath(image))
            # An image Qt could not decode is in unsorted/ already
            if error.reason is not DeckWriteReason.UNREADABLE_IMAGE:
                with contextlib.suppress(DeckWriteError, OSError):
                    place_unsorted(deck, image)
        except OSError:
            failed.append(os.fspath(image))
        advance()
    for image in unsorted:
        if _is_unsorted(deck, Path(image)):
            advance()
            continue
        try:
            place_unsorted(deck, image)
        except (DeckWriteError, OSError):
            failed.append(os.fspath(image))
        advance()
    return failed


def oriented_height(image):
    """image's height as shown, once its orientation is applied"""
    return _read_header(Path(image))[0]


def place_unsorted(deck, image):
    """Copy image into unsorted/"""
    deck = _checked(deck)
    image = Path(image)
    _read_header(image)
    unsorted = deck / UNSORTED
    unsorted.mkdir(exist_ok=True)
    target = _free_name(unsorted, image.name)
    with _atomic(target) as temporary:
        shutil.copyfile(image, temporary)
    return target.name


def discard_unsorted(deck, name):
    """Delete one image from unsorted/"""
    deck = _checked(deck)
    if not name or name != Path(name).name or name in (".", ".."):
        raise ValueError(f"not a file name in unsorted/: {name!r}")
    (deck / UNSORTED / name).unlink()


def refresh(deck, progress=None):
    """Make h<H>/ match source/, finishing whatever an interrupted call left"""
    _sync(_checked(deck), progress)


# -- the deck's layout ---------------------------------------------------------------------


def _checked(deck):
    """deck as a Path, once it is known to be a deck created here; strays from a crash removed"""
    deck = Path(deck)
    try:
        with open(deck / DECK_TOML, encoding="utf-8") as handle:
            table = tomlkit.parse(handle.read()).get("deck")
    except FileNotFoundError:
        raise DeckWriteError(
            DeckWriteReason.NOT_CREATED_HERE, f"no {DECK_TOML} in {deck}"
        ) from None
    except ValueError as error:  # not TOML, or not UTF-8
        raise DeckWriteError(DeckWriteReason.NOT_CREATED_HERE, f"{deck}: {error}") from error
    identifier = table.get("identifier") if isinstance(table, Mapping) else None
    if not isinstance(identifier, str) or not identifier.startswith(IDENTIFIER_PREFIX):
        raise DeckWriteError(DeckWriteReason.NOT_CREATED_HERE, f"{deck} has no private identifier")
    if _roots(deck) and not (deck / SOURCE).is_dir():
        raise DeckWriteError(
            DeckWriteReason.NOT_CREATED_HERE, f"{deck} has images but no {SOURCE}/"
        )
    _remove_strays(deck)
    return deck


def _remove_strays(deck):
    for entry in deck.iterdir():
        if entry.is_dir() and _PARTIAL.fullmatch(entry.name):
            shutil.rmtree(entry)
        elif entry.name.startswith(f".{DECK_TOML}."):
            entry.unlink()
    for top in (deck / SOURCE, deck / UNSORTED, *_roots(deck)):
        for directory, _, files in os.walk(top):
            for name in files:
                if name.startswith("."):
                    os.unlink(os.path.join(directory, name))


def _roots(deck):
    """The raster roots in deck, h<H>/ for every H found"""
    with contextlib.suppress(FileNotFoundError):
        return [entry for entry in deck.iterdir() if entry.is_dir() and _ROOT.fullmatch(entry.name)]
    return []


def _height_of(root):
    return int(_ROOT.fullmatch(root.name).group(1))


def _check_card_id(card_id):
    if card_id not in _SLOTS:
        raise DeckWriteError(DeckWriteReason.UNKNOWN_CARD, repr(card_id))


def _check_slot(deck, card_id):
    _check_card_id(card_id)
    with open(deck / DECK_TOML, encoding="utf-8") as handle:
        excluded = tomlkit.parse(handle.read()).get("excluded_cards", {})
    if card_id in excluded.get("cards", ()):
        raise DeckWriteError(DeckWriteReason.NOT_IN_DECK, card_id)


def _subpath(card_id):
    """card_id's path under an image root, without an extension"""
    return Path(*card_id.split("."))


def _slot_folder(deck, card_id):
    """Where card_id's original is kept, under the name it came with"""
    return deck / SOURCE / _subpath(card_id)


def _originals(deck, card_id):
    """The files in card_id's folder in source/"""
    with contextlib.suppress(FileNotFoundError, NotADirectoryError):
        return [
            entry
            for entry in _slot_folder(deck, card_id).iterdir()
            if entry.is_file() and not entry.name.startswith(".")
        ]
    return []


def _files_with_stem(path):
    """The files in path's directory whose stem is path's name, whatever their extension"""
    with contextlib.suppress(FileNotFoundError):
        return [
            entry
            for entry in path.parent.iterdir()
            if entry.is_file() and not entry.name.startswith(".") and entry.stem == path.name
        ]
    return []


def _clear_stem(path):
    for entry in _files_with_stem(path):
        entry.unlink()


def _source_suffix(image):
    suffix = image.suffix.lower()
    if suffix:
        return suffix
    image_format = _read_header(image)[1]
    return _BASELINE.get(image_format, f".{image_format}")


def _is_unsorted(deck, image):
    return image.resolve().parent == (deck / UNSORTED).resolve()


def _free_name(directory, name):
    """directory/name, or <stem>-2, -3… where that is taken"""
    candidate = directory / name
    stem, suffix = Path(name).stem, Path(name).suffix
    number = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{number}{suffix}"
        number += 1
    return candidate


def _to_unsorted(deck, path):
    unsorted = deck / UNSORTED
    unsorted.mkdir(exist_ok=True)
    os.replace(path, _free_name(unsorted, path.name))


@contextlib.contextmanager
def _atomic(target):
    """A temporary path beside target, renamed over target once written"""
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    os.close(descriptor)
    try:
        yield temporary
        with open(temporary, "rb+") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


# -- images --------------------------------------------------------------------------------


def _reader(path):
    reader = QImageReader(os.fspath(path))
    reader.setDecideFormatFromContent(True)
    reader.setAutoTransform(True)
    return reader


def _read_header(path):
    """(oriented height, Qt's format name, whether it is stored rotated or flipped)"""
    reader = _reader(path)
    image_format = bytes(reader.format()).decode().lower()
    if not reader.canRead() or not image_format or image_format in _VECTOR:
        raise DeckWriteError(DeckWriteReason.UNREADABLE_IMAGE, os.fspath(path))
    size = reader.size()
    transformation = reader.transformation()
    rotated = bool(transformation & QImageIOHandler.Transformation.TransformationRotate90)
    height = size.width() if rotated else size.height()
    if size.isEmpty():
        # A format whose header doesn't give its size; read() applies the orientation itself
        height = reader.read().height()
        transformation = reader.transformation()
    if height <= 0:
        raise DeckWriteError(DeckWriteReason.UNREADABLE_IMAGE, os.fspath(path))
    transformed = transformation != QImageIOHandler.Transformation.TransformationNone
    return height, image_format, transformed


def _derived_suffix(image_format):
    return _BASELINE.get(image_format, ".png")


def _derive(source, height, image_format, transformed, target_height, target):
    """Write source at target_height to target: a byte copy where it already is, else encoded"""
    if height == target_height and image_format in _BASELINE and not transformed:
        with _atomic(target) as temporary:
            shutil.copyfile(source, temporary)
        return
    reader = _reader(source)
    image = reader.read()
    if image.isNull():
        raise DeckWriteError(DeckWriteReason.UNREADABLE_IMAGE, f"{source}: {reader.errorString()}")
    if image.height() != target_height:
        image = image.scaledToHeight(target_height, Qt.TransformationMode.SmoothTransformation)
    out_format = image_format if image_format in _BASELINE else "png"
    encoded = QByteArray()
    buffer = QBuffer(encoded)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, out_format.encode())
    if out_format in _QUALITY:
        writer.setQuality(_QUALITY[out_format])
    if not writer.write(image):
        raise OSError(f"could not encode {source} as {out_format}: {writer.errorString()}")
    buffer.close()
    with _atomic(target) as temporary:
        Path(temporary).write_bytes(bytes(encoded))


# -- keeping h<H>/ in step with source/ ----------------------------------------------------


def _sources(deck):
    """{card_id: its one file in source/}; where a slot holds several, the newest stays"""
    found = {}
    for card_id in _SLOTS:
        files = _originals(deck, card_id)
        if not files:
            continue
        files.sort(key=lambda entry: entry.stat().st_mtime_ns, reverse=True)
        found[card_id] = files[0]
        for older in files[1:]:
            _to_unsorted(deck, older)
    return found


def _sync(deck, progress):
    sources = {}
    for card_id, path in _sources(deck).items():
        try:
            sources[card_id] = (path, *_read_header(path))
        except DeckWriteError:
            log.warning("Deriving nothing from unreadable %s", path)
    roots = _roots(deck)
    if not sources:
        for root in roots:
            shutil.rmtree(root)
        return
    target_height = min(HEIGHT_CAP, min(header[1] for header in sources.values()))
    current = next((root for root in roots if _height_of(root) == target_height), None)
    if current is None:
        partial = deck / f".h{target_height}.partial"
        _write_derived(partial, sources, target_height, progress)
        current = deck / f"h{target_height}"
        os.replace(partial, current)
    else:
        stale = {
            card_id: header
            for card_id, header in sources.items()
            if not _is_current(current, card_id, header)
        }
        _write_derived(current, stale, target_height, progress)
        _remove_orphans(current, sources)
    for root in roots:
        if root != current:
            shutil.rmtree(root)


def _is_current(root, card_id, header):
    source, _, image_format, _ = header
    expected = root / _subpath(card_id)
    expected = expected.with_name(expected.name + _derived_suffix(image_format))
    files = _files_with_stem(root / _subpath(card_id))
    if files != [expected]:
        return False
    return expected.stat().st_mtime_ns >= source.stat().st_mtime_ns


def _write_derived(root, stale, target_height, progress):
    total = len(stale)
    for done, (card_id, (source, height, image_format, transformed)) in enumerate(stale.items()):
        if progress is not None:
            progress(done, total)
        target = root / _subpath(card_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        _clear_stem(target)
        target = target.with_name(target.name + _derived_suffix(image_format))
        try:
            _derive(source, height, image_format, transformed, target_height, target)
        except DeckWriteError:
            log.warning("Could not decode %s, so its card has no image", source)
    if progress is not None and total:
        progress(total, total)


def _remove_orphans(root, sources):
    """Derived images whose slot has no source, and anything not in a slot"""
    keep = set()
    for card_id in sources:
        keep.update(_files_with_stem(root / _subpath(card_id)))
    for directory, _, files in os.walk(root):
        for name in files:
            path = Path(directory) / name
            if path not in keep:
                path.unlink()
