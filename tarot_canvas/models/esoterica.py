"""
This module is expected to become a thin call into arcana-tarot once that is done
"""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from tarot_canvas.models.card_ids import COURTS, PIPS
from tarot_canvas.models.esoterica_registry import (
    CORRESPONDENCES,
    PASSAGES,
    Role,
    role_of,
    sort_key,
)
from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import get_esoterica_directories

SUPPORTED_SCHEMA_MAJORS = {"1"}


class Passage(NamedTuple):
    """One source's text for one card, ready to render."""

    source_name: str
    author: str | None
    text: str


@dataclass(frozen=True)
class Entry:
    """One passage or correspondence (exactly from TOML)."""

    slot: str
    key: str  # the full dotted entry key
    role: Role | None  # None for a key the registry doesn't know
    value: str | int | float | bool | tuple


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


_VALIDATORS = {PASSAGES: _is_passage_value, CORRESPONDENCES: _is_correspondence_value}


def _walk(table, prefix=""):
    """Yield (dotted key, value) for every leaf, in file order.."""
    for key, value in table.items():
        if isinstance(value, dict):
            yield from _walk(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}", value


def _flatten(target):
    """One target's passages and correspondences in registry order."""
    found = []
    file_index = 0
    for slot in (PASSAGES, CORRESPONDENCES):
        table = target.get(slot)
        if not isinstance(table, dict):
            continue
        for key, value in _walk(table):
            file_index += 1
            if not _VALIDATORS[slot](value):
                continue
            if isinstance(value, list):
                value = tuple(value)
            entry = Entry(slot, key, role_of(slot, key), value)
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

    return {
        "path": path,
        "meta": meta,
        "cards": cards,
        "groups": groups,
        "name": meta.get("name") or path.stem,
        "author": meta.get("author") or None,
    }


class EsotericaManager:
    def __init__(self, roots=None):
        # Keyed by path relative to the root it was found under
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

            for path in sorted(root.glob("**/*.toml")):
                key = str(path.relative_to(root))
                if key in self.sources:
                    continue  # The first root wins.
                source = _read_source(path)
                if source is not None:
                    self.sources[key] = source

        logger.info(f"Loaded {len(self.sources)} esoterica sources")

    def has_sources(self):
        """Whether any file could be read. A file in the older format doesn't count."""
        return bool(self.sources)

    def get_passages_for_card(self, card_id):
        canonical = str(card_id).split(":", 1)[0]

        passages = []
        for source in self.sources.values():
            target = source["cards"].get(canonical)
            if not isinstance(target, dict):
                continue
            slot = target.get("passages")
            if not isinstance(slot, dict):
                continue
            text = slot.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            passages.append(Passage(source["name"], source["author"], text))

        return passages

    def read_card(self, card_id):
        """
        What every source says about a card
        """
        canonical = str(card_id).split(":", 1)[0]

        readings = []
        for source in self.sources.values():
            target = source["cards"].get(canonical)
            entries = _flatten(target) if isinstance(target, dict) else ()
            groups = _read_groups(source["groups"], canonical)
            if not _is_renderable(entries) and not groups:
                continue
            readings.append(SourceReading(source["name"], source["author"], entries, groups))

        return readings


_manager = None


def get_esoterica_manager():
    global _manager
    if _manager is None:
        _manager = EsotericaManager()
    return _manager
