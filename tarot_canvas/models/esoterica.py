"""
This module is expected to become a thin call into arcana-tarot once that is done
"""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from tarot_canvas.models.card_ids import COURTS, PIPS
from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.models.esoterica_registry import (
    CORRESPONDENCES,
    FAMILIES,
    GROUPS,
    PASSAGES,
    SYMBOLS,
    Role,
    role_of,
    sort_key,
)
from tarot_canvas.settings import get_esoterica_disabled
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import get_esoterica_directories

SUPPORTED_SCHEMA_MAJORS = {"1"}

RWS = "land.arcana/pattern/rider-waite-smith"
TDM = "land.arcana/pattern/tarot-de-marseille"

# Where a card a source wrote for one pattern sits in a deck of the other: for a pair of
# patterns, canonical ID -> the ID the source wrote that card at
RESEATS = {
    frozenset({RWS, TDM}): {
        "major_arcana.08": "major_arcana.11",
        "major_arcana.11": "major_arcana.08",
    },
}


@dataclass(frozen=True)
class Entry:
    """One passage, correspondence or symbol (exactly from TOML)."""

    slot: str
    key: str  # the full dotted entry key; a symbol's bare name
    role: Role | None  # None for a key the registry doesn't know
    value: str | int | float | bool | tuple
    label: str | None = None  # a symbol's printed heading, if the source gives one


@dataclass(frozen=True)
class GroupReading:
    """What a single source says about a group the card belongs to.."""

    group: str
    family: str
    entries: tuple[Entry, ...]


@dataclass(frozen=True)
class SourceReading:
    """Everything one source says about one card."""

    name: str
    author: str | None
    entries: tuple[Entry, ...]
    groups: tuple[GroupReading, ...]
    # The source is about the deck being read for
    about_deck: bool = False
    # The canonical ID the entries were read from, when it isn't the card's
    written_at: str | None = None
    # The source and the deck are of patterns with no known seating between them
    divergent: bool = False
    # The pattern the source declares, when it was read for a deck
    pattern: str | None = None


def _is_passage_text(value):
    return isinstance(value, str) and bool(value.strip())


def _is_passage_value(value):
    if isinstance(value, list):
        return bool(value) and all(_is_passage_text(item) for item in value)
    return _is_passage_text(value)


def _is_correspondence_scalar(value):
    if isinstance(value, str):
        return bool(value.strip())
    return isinstance(value, bool | int | float)


def _is_correspondence_value(value):
    if isinstance(value, list):
        return bool(value) and all(_is_correspondence_scalar(item) for item in value)
    return _is_correspondence_scalar(value)


_VALIDATORS = {
    PASSAGES: _is_passage_value,
    CORRESPONDENCES: _is_correspondence_value,
    SYMBOLS: _is_passage_text,
}


def _walk(table, prefix=""):
    """Yield (dotted key, value) for every leaf, in file order.."""
    for key, value in table.items():
        if isinstance(value, dict):
            yield from _walk(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}", value


def _is_legacy_symbols(key, value):
    """passages.symbols.<name>, the draft spelling of the symbols slot, which is no longer read"""
    return key == SYMBOLS and isinstance(value, dict)


def _has_legacy_symbols(target):
    passages = target.get(PASSAGES)
    if not isinstance(passages, dict):
        return False
    return any(_is_legacy_symbols(key, value) and value for key, value in passages.items())


def _items(slot, table):
    """(key, value, label) for every entry in a slot, in file order. Only a symbol has a label."""
    if slot != SYMBOLS:
        if slot == PASSAGES:
            table = {k: v for k, v in table.items() if not _is_legacy_symbols(k, v)}
        for key, value in _walk(table):
            yield key, value, None
        return
    # Each direct child is one symbol: a table with text, and its printed heading if it has one
    for name, symbol in table.items():
        if not isinstance(symbol, dict):
            symbol = {}
        label = symbol.get("label")
        yield name, symbol.get("text"), label if _is_passage_text(label) else None


def _flatten(target):
    """One target's passages, correspondences and symbols in registry order."""
    found = []
    file_index = 0
    for slot in (PASSAGES, CORRESPONDENCES, SYMBOLS):
        table = target.get(slot)
        if not isinstance(table, dict):
            continue
        for key, value, label in _items(slot, table):
            file_index += 1
            if not _VALIDATORS[slot](value):
                continue
            if isinstance(value, list):
                value = tuple(value)
            entry = Entry(slot, key, role_of(slot, key), value, label)
            found.append((sort_key(slot, key, file_index), entry))
    found.sort(key=lambda pair: pair[0])
    return tuple(entry for _, entry in found)


def _is_renderable(entries):
    return any(entry.role is not None for entry in entries)


def groups_for(card_id):
    """
    The builtin groups a canonical card ID belongs to, narrowest first.
    """
    parts = str(card_id).split(".")
    if parts[0] == "major_arcana":
        return ("arcana.major", "all")
    if parts[0] != "minor_arcana" or len(parts) != 3:
        return ("all",)

    _, suit, rank = parts
    groups = [f"suits.{suit}", f"ranks.{rank}"]

    # A custom rank is in neither class
    if rank in PIPS:
        groups.append("classes.pip")
    elif rank in COURTS:
        groups.append("classes.court")
    groups += ["arcana.minor", "all"]
    return tuple(groups)


def _custom_groups_for(groups, canonical):
    """A source's own groups that list the card, in file order."""
    custom = groups.get("custom")
    if not isinstance(custom, dict):
        return ()
    found = []
    for name, target in custom.items():
        if not isinstance(target, dict):
            continue
        cards = target.get("cards")
        if isinstance(cards, list) and canonical in cards:
            found.append(f"custom.{name}")
    return tuple(found)


def _group_target(groups, group):
    """The table for a group key such as suits.cups or all, or None."""
    node = groups
    for part in group.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node if isinstance(node, dict) else None


def _read_groups(groups, canonical):
    readings = []
    for group in _custom_groups_for(groups, canonical) + groups_for(canonical):
        target = _group_target(groups, group)
        if target is None:
            continue
        entries = _flatten(target)
        if _is_renderable(entries):
            readings.append(GroupReading(group, group.split(".", 1)[0], entries))
    return tuple(readings)


def _group_targets(groups):
    """Every group table in a source, whether or not any card is in it"""
    for family, node in groups.items():
        if not isinstance(node, dict):
            continue
        if family == "all":
            yield node
            continue
        yield from (target for target in node.values() if isinstance(target, dict))


def _families_in(source):
    """The families a source has on some card or group"""
    found = set()
    targets = [target for target in source["cards"].values() if isinstance(target, dict)]
    for target in targets:
        found.update(FAMILIES.get(entry.role) for entry in _flatten(target))
    for target in _group_targets(source["groups"]):
        entries = _flatten(target)
        if _is_renderable(entries):
            found.add(GROUPS)
            found.update(FAMILIES.get(entry.role) for entry in entries)
    found.discard(None)
    return found


def _read_related(path, meta):
    """[meta].related as (the pattern or None, the frozenset of `about` targets)."""
    related = meta.get("related")
    # An overlay takes its relations from the source it translates
    if related is None or "translates" in meta:
        return None, frozenset()
    if not isinstance(related, list):
        logger.warning(f"{path}: [meta].related is not an array, so it is not read")
        return None, frozenset()

    patterns = []
    about = set()
    for entry in related:
        target = entry.get("target") if isinstance(entry, dict) else None
        if not isinstance(target, str) or not target.strip():
            logger.warning(f"{path}: an entry in [meta].related has no target; skipping it")
            continue
        if entry.get("rel") == "pattern":
            patterns.append(target.strip())
        elif entry.get("rel") == "about":
            about.add(target.strip())

    if len(patterns) > 1:
        logger.warning(
            f"{path}: [meta].related names more than one pattern, so it is read as having none"
        )
        patterns = []
    return (patterns[0] if patterns else None), frozenset(about)


def _is_deck_identifier(target):
    """<ns>/deck/<name>, as opposed to a pattern's <ns>/pattern/<name>"""
    parts = target.split("/")
    return len(parts) == 3 and parts[1] == "deck"


def _decks_about(source):
    return {target for target in source["about"] if _is_deck_identifier(target)}


def _is_shown_on(source, identifier):
    """A source about some decks is read only on one of them"""
    decks = _decks_about(source)
    return not decks or identifier in decks


def _seat(canonical, deck_pattern, source_pattern):
    """(the ID the source wrote this card at, whether the patterns have no known seating)"""
    if deck_pattern is None or source_pattern is None or deck_pattern == source_pattern:
        return canonical, False
    swaps = RESEATS.get(frozenset({deck_pattern, source_pattern}))
    if swaps is None:
        return canonical, True
    return swaps.get(canonical, canonical), False


def _read_source(path):
    """Parse one file, or return None if can't be parsed."""
    try:
        with open(path, "rb") as f:
            content = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.debug(f"Not readable as an esoterica source: {path} ({e})")
        return None

    meta = content.get("meta")
    if not isinstance(meta, dict):
        meta = {}

    cards = content.get("card")

    if not isinstance(cards, dict):
        if "passages" in content or "id" in meta:
            logger.warning(
                f"{path}: this is the older esoterica format, which is no longer read. "
                f'Passages now live under [card."<canonical id>".passages].'
            )
        return None

    schema_version = meta.get("schema_version")
    if isinstance(schema_version, str):
        major = schema_version.split(".")[0]
        if major not in SUPPORTED_SCHEMA_MAJORS:
            logger.warning(f"{path}: schema_version {schema_version!r} is not supported; skipping")
            return None

    groups = content.get("group")
    if not isinstance(groups, dict):
        groups = {}

    targets = [*cards.values(), *_group_targets(groups)]
    if any(_has_legacy_symbols(target) for target in targets if isinstance(target, dict)):
        logger.warning(
            f"{path}: symbols under passages are a draft spelling, which is no longer read. "
            f'Symbols now live under [card."<canonical id>".symbols.<name>], with text = "…".'
        )

    pattern, about = _read_related(path, meta)

    return {
        "path": path,
        "meta": meta,
        "pattern": pattern,
        "about": about,
        "cards": cards,
        "groups": groups,
        "name": meta.get("name") or path.stem,
        "author": meta.get("author") or None,
    }


def _identifier(meta):
    identifier = meta.get("identifier")
    if isinstance(identifier, str) and identifier.strip():
        return identifier.strip()
    return None


class EsotericaManager:
    def __init__(self, roots=None):
        # None means the path helper's roots, looked up again at each load
        self._roots = roots
        # Keyed by [meta].identifier: in root order, then by path within a root.
        # Disabled sources are kept; they are filtered out on each read.
        self.sources = {}
        self.load_sources(roots)

    def load_sources(self, roots=None):
        self.sources = {}

        if roots is None:
            roots = get_esoterica_directories()

        for index, root in enumerate(roots):
            root = Path(root)
            if index == 0:
                # Give the user somewhere to put files.
                os.makedirs(root, exist_ok=True)
            if not root.is_dir():
                continue

            # Identifier -> the path that claimed it in this root
            claimed = {}
            for path in sorted(root.glob("**/*.toml")):
                source = _read_source(path)
                if source is None:
                    continue
                identifier = _identifier(source["meta"])
                if identifier is None:
                    logger.warning(f"{path}: [meta].identifier is missing, so it is not read")
                    continue
                if identifier in claimed:
                    logger.warning(
                        f"{path} and {claimed[identifier]} have the same identifier "
                        f"{identifier!r}; only {claimed[identifier]} is read"
                    )
                    continue
                if identifier in self.sources:
                    # An earlier root wins, and that is not reported
                    logger.debug(f"{path}: {identifier!r} is shadowed by an earlier root")
                    continue
                claimed[identifier] = path
                source["root"] = root
                source["families"] = frozenset(_families_in(source))
                self.sources[identifier] = source

        logger.info(f"Loaded {len(self.sources)} esoterica sources")

    def reload(self):
        """Read every root again, for files added, removed or changed since the last load"""
        self.load_sources(self._roots)
        esoterica_events().sources_changed.emit()

    def _enabled(self):
        disabled = set(get_esoterica_disabled())
        return [source for key, source in self.sources.items() if key not in disabled]

    def has_sources(self):
        """Whether any source could be read, enabled or not. A file with no identifier, or in
        the older format, doesn't count."""
        return bool(self.sources)

    def has_enabled_sources(self):
        """Whether any source that could be read is turned on"""
        return bool(self._enabled())

    def families_present(self):
        """The family ids (and `groups`) some enabled source has on some card or group"""
        return frozenset().union(*(source["families"] for source in self._enabled()))

    def read_card(self, card_id, deck=None):
        """
        What every source says about a card. Given the deck it is shown on, a source about
        another deck is left out, one about this deck comes first, and a card is read from
        where the source's pattern seats it.
        """
        canonical = str(card_id).split(":", 1)[0]

        sources = self._enabled()
        if deck is not None:
            identifier = deck.get_identifier()
            sources = [source for source in sources if _is_shown_on(source, identifier)]
            sources.sort(key=lambda source: identifier not in _decks_about(source))

        readings = []
        for source in sources:
            about_deck = False
            written_at, divergent = canonical, False
            if deck is not None:
                about_deck = identifier in _decks_about(source)
                written_at, divergent = _seat(canonical, deck.get_pattern(), source["pattern"])
            target = source["cards"].get(written_at)
            entries = _flatten(target) if isinstance(target, dict) else ()
            groups = _read_groups(source["groups"], canonical)
            if not _is_renderable(entries) and not groups:
                continue
            readings.append(
                SourceReading(
                    source["name"],
                    source["author"],
                    entries,
                    groups,
                    about_deck=about_deck,
                    written_at=written_at if written_at != canonical else None,
                    divergent=divergent,
                    pattern=source["pattern"] if deck is not None else None,
                )
            )

        return readings


_manager = None


def get_esoterica_manager():
    global _manager
    if _manager is None:
        _manager = EsotericaManager()
    return _manager
