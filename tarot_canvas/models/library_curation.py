"""Which Library items the user has pinned, hidden, turned off, and the decks made here (stored in library.toml)"""

import logging
import os
from pathlib import Path

from tarot_canvas.models import spreads
from tarot_canvas.models.deck_events import deck_events
from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.models.reading_events import reading_events
from tarot_canvas.models.spread_events import spread_events
from tarot_canvas.models.toml_files import load_table, write_toml
from tarot_canvas.settings import get_settings, string_list
from tarot_canvas.utils.path_helper import get_data_directory

log = logging.getLogger(__name__)

CURATION_SUBPATH = "tarot-canvas/library.toml"

SPREADS = "spreads"
READINGS = "readings"
ESOTERICA = "esoterica"
DECKS = "decks"

PINNED = "pinned"
HIDDEN = "hidden"
DISABLED = "disabled"
HANDMADE = "handmade"

INCLUDED_PREFIX = "included/"

# Where esoterica's disabled sources were kept before this file, read once and removed
LEGACY_ESOTERICA_DISABLED_KEY = "esoterica/disabled"

# (the file's stat when read, its table); a write or a hand-edit changes the stat
_cache = None


def curation_file():
    return get_data_directory(CURATION_SUBPATH)


def _stamp(file):
    try:
        status = os.stat(file)
    except OSError:
        return None
    return status.st_ino, status.st_mtime_ns, status.st_size


def _load():
    """The file's table, {} when there is none, or None when it can't be read"""
    global _cache
    file = curation_file()
    stamp = _stamp(file)
    if stamp is None:
        _cache = None
        return {}
    if _cache is not None and _cache[0] == (file, stamp):
        return _cache[1]
    try:
        table = load_table(file)
    except (OSError, ValueError) as error:
        log.warning("Reading no curation from unreadable %s: %s", file, error)
        table = None
    _cache = ((file, stamp), table)
    return table


def keys(view, kind):
    """The keys in [view] kind, in the file's order; [] when absent or unreadable"""
    table = _load() or {}
    section = table.get(view)
    if not isinstance(section, dict):
        return []
    listed = section.get(kind)
    if not isinstance(listed, list):
        return []
    return [key for key in listed if isinstance(key, str)]


def _write(change):
    """Re-read the file, let change(table) edit it, and write it back if it changed"""
    global _cache
    _cache = None  # another window may have written since
    current = _load() or {}
    table = {
        name: dict(value) if isinstance(value, dict) else value for name, value in current.items()
    }
    if not change(table):
        return False
    file = curation_file()
    try:
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        write_toml(file, table)
    except (OSError, TypeError, ValueError) as error:
        log.error("Could not write curation to %s: %s", file, error)
        return False
    _cache = None
    return True


def _set_list(table, view, kind, listed):
    section = table.get(view)
    if not isinstance(section, dict):
        section = table[view] = {}
    if listed:
        section[kind] = listed
    else:
        section.pop(kind, None)
        if not section:
            del table[view]


def update(view, add=(), remove=()):
    """Add and remove keys across kinds of one view"""

    def change(table):
        changed = False
        for kind in {kind for kind, _ in (*add, *remove)}:
            before = keys_in(table, view, kind)
            after = [key for key in before if (kind, key) not in remove]
            after += [key for k, key in add if k == kind and key not in after]
            if after != before:
                _set_list(table, view, kind, after)
                changed = True
        return changed

    return _write(change)


def keys_in(table, view, kind):
    section = table.get(view)
    listed = section.get(kind) if isinstance(section, dict) else None
    return [key for key in listed if isinstance(key, str)] if isinstance(listed, list) else []


# -- spreads ------------------------------------------------------------------------------


def spread_key(path):
    """A spread's key: its folder's name, under included/ for one that ships with the app"""
    path = Path(path)
    return INCLUDED_PREFIX + path.name if spreads.is_included(path) else path.name


def spread_pins():
    return set(keys(SPREADS, PINNED))


def spread_hides():
    return set(keys(SPREADS, HIDDEN))


def set_spread_pinned(path, pinned):
    """Pinning a hidden spread unhides it"""
    key = spread_key(path)
    if pinned:
        changed = update(SPREADS, add=[(PINNED, key)], remove=[(HIDDEN, key)])
    else:
        changed = update(SPREADS, remove=[(PINNED, key)])
    if changed:
        spread_events().spreads_changed.emit()


def set_spread_hidden(path, hidden):
    """Hiding a pinned spread unpins it. Only an included spread is hidden"""
    key = spread_key(path)
    if hidden:
        if not key.startswith(INCLUDED_PREFIX):
            log.error("Refusing to hide a spread of the user's own, %s", path)
            return
        changed = update(SPREADS, add=[(HIDDEN, key)], remove=[(PINNED, key)])
    else:
        changed = update(SPREADS, remove=[(HIDDEN, key)])
    if changed:
        spread_events().spreads_changed.emit()


def forget_spread(path):
    """A spread deleted through the app takes its pin with it"""
    key = spread_key(path)
    if update(SPREADS, remove=[(PINNED, key), (HIDDEN, key)]):
        spread_events().spreads_changed.emit()


# -- readings -----------------------------------------------------------------------------


def reading_key(path):
    return Path(path).name


def reading_pins():
    return set(keys(READINGS, PINNED))


def set_reading_pinned(path, pinned):
    change = [(PINNED, reading_key(path))]
    if update(READINGS, add=change) if pinned else update(READINGS, remove=change):
        reading_events().readings_changed.emit()


def forget_reading(path):
    """A reading deleted through the app takes its pin with it"""
    if update(READINGS, remove=[(PINNED, reading_key(path))]):
        reading_events().readings_changed.emit()


# -- decks ------------------------------------------------------------------------------


def deck_key(path):
    return Path(path).name


def handmade_decks():
    """The folder names of the decks made in this app"""
    return set(keys(DECKS, HANDMADE))


def is_handmade(path):
    """Whether the deck at path was made in this app; a listed folder that is gone was not"""
    return Path(path).is_dir() and deck_key(path) in handmade_decks()


def add_handmade_deck(path):
    update(DECKS, add=[(HANDMADE, deck_key(path))])


def deck_pins():
    """The identifiers of the pinned decks"""
    return set(keys(DECKS, PINNED))


def deck_hides():
    """The identifiers of the hidden decks; pinned wins over a hand-edit that also hides"""
    return set(keys(DECKS, HIDDEN)) - deck_pins()


def set_deck_pinned(identifier, pinned):
    """Pinning a hidden deck unhides it"""
    if not identifier:
        log.error("Refusing to pin or unpin a deck without an identifier")
        return
    if pinned:
        changed = update(DECKS, add=[(PINNED, identifier)], remove=[(HIDDEN, identifier)])
    else:
        changed = update(DECKS, remove=[(PINNED, identifier)])
    if changed:
        deck_events().decks_changed.emit()


def set_deck_hidden(identifier, hidden):
    """Hiding a pinned deck unpins it"""
    if not identifier:
        log.error("Refusing to hide or unhide a deck without an identifier")
        return
    if hidden:
        changed = update(DECKS, add=[(HIDDEN, identifier)], remove=[(PINNED, identifier)])
    else:
        changed = update(DECKS, remove=[(HIDDEN, identifier)])
    if changed:
        deck_events().decks_changed.emit()


def forget_deck(path, identifier=None):
    """A deck removed through the app takes what is kept about it with it

    Its pin and hide stay while another deck has the identifier.
    """
    # Importing the library scans the disk, and esoterica imports this module
    from tarot_canvas.models.deck_library import deck_library

    forgotten = [(HANDMADE, deck_key(path))]
    if identifier and not deck_library.find_by_identifier(identifier):
        forgotten += [(PINNED, identifier), (HIDDEN, identifier)]
    update(DECKS, remove=forgotten)


# -- esoterica ----------------------------------------------------------------------------


def _migrate_esoterica_disabled():
    """Move esoterica/disabled out of QSettings (one-time)"""
    settings = get_settings()
    if not settings.contains(LEGACY_ESOTERICA_DISABLED_KEY):
        return None
    legacy = string_list(LEGACY_ESOTERICA_DISABLED_KEY)
    table = _load()
    if table is None:
        return legacy  # a hand-edit's typo isn't overwritten at launch

    def change(table):
        section = table.get(ESOTERICA)
        if isinstance(section, dict) and DISABLED in section:
            return False  # already carried, by another window
        _set_list(table, ESOTERICA, DISABLED, legacy)
        return True

    if not legacy or _write(change) or keys(ESOTERICA, DISABLED):
        settings.remove(LEGACY_ESOTERICA_DISABLED_KEY)
        return None
    return legacy


def esoterica_disabled():
    """The identifiers of the esoterica sources that are turned off"""
    legacy = _migrate_esoterica_disabled()
    return legacy if legacy is not None else keys(ESOTERICA, DISABLED)


def set_esoterica_disabled(ids):
    """ids replace the list, identifiers this run didn't read included"""
    ids = list(dict.fromkeys(ids))

    def change(table):
        _set_list(table, ESOTERICA, DISABLED, ids)
        return True

    # The user's choice supersedes whatever QSettings still held
    if _write(change):
        get_settings().remove(LEGACY_ESOTERICA_DISABLED_KEY)
    esoterica_events().sources_changed.emit()
