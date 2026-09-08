"""
This module is expected to become a thin call into arcana-tarot once that is done
"""

import os
import tomllib
from pathlib import Path
from typing import NamedTuple

from tarot_canvas.utils.logger import logger
from tarot_canvas.utils.path_helper import get_esoterica_directories

SUPPORTED_SCHEMA_MAJORS = {"1"}


class Passage(NamedTuple):
    """One source's text for one card, ready to render."""

    source_name: str
    author: str | None
    text: str


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

    return {
        "path": path,
        "meta": meta,
        "cards": cards,
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


_manager = None


def get_esoterica_manager():
    global _manager
    if _manager is None:
        _manager = EsotericaManager()
    return _manager
