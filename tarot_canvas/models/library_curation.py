"""Which Library items the user has pinned, hidden or turned off: tarot-canvas/library.toml

Curation is lists of stable keys, one table per Library view. It is user data beside
spreads/ and readings/, so it travels with them; settings that describe one machine stay in
QSettings. A key with nothing behind it is kept, so a pin can arrive before its reading.
"""

import logging
import os
from pathlib import Path

from tarot_canvas.models import spreads
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

PINNED = "pinned"
HIDDEN = "hidden"
DISABLED = "disabled"

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
    """Re-read the file, let change(table) edit it, and write it back if it changed

    An unreadable file is replaced only by a real change, which is the user's; until then it is
    left for them to fix. Unknown tables and keys are carried through.
    """
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
    """Add and remove keys across kinds of one view in one write; whether anything changed

    add and remove are (kind, key) pairs. A key is added at the end, and never twice.
    """

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


# -- esoterica ----------------------------------------------------------------------------


def _migrate_esoterica_disabled():
    """Move esoterica/disabled out of QSettings, once

    The key stays put while the file can't be read or written, and the next read retries.
    Returns the legacy list while it is still the one in force, else None.
    """
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
