"""Export a handmade deck"""

import shutil
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from tarot_canvas.models import deck_writer
from tarot_canvas.models.deck_container import DECK_TOML, pack_container
from tarot_canvas.models.deck_install import install_dir_name
from tarot_canvas.models.deck_validation import Verdict, validate_deck

CONTAINER_SUFFIX = ".tarotdeck"
_PACKED = "export.tarotdeck"
_DECK = "deck"


@dataclass(frozen=True)
class Staged:
    folder: Path  # removed by discard()
    verdict: Verdict

    @property
    def deck(self):
        return self.folder / _DECK


def stage(deck, staging_root, excluded=()):
    """A copy of deck's exported files at staging_root, with the cards in excluded listed in
    its [excluded_cards]; the working deck.toml is not touched"""
    deck = Path(deck)
    files = deck_writer.exported_files(deck)
    with open(deck / DECK_TOML, "rb") as handle:
        table = tomllib.load(handle).get("deck", {})
    name = install_dir_name(table.get("identifier"), deck.name)
    staging_root = Path(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=f"{name}.export.", dir=staging_root))
    try:
        for relative in files:
            target = folder / _DECK / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(deck / relative, target)
        if excluded:
            deck_writer.list_excluded(folder / _DECK / DECK_TOML, excluded)
        return Staged(folder, validate_deck(folder / _DECK))
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def write(staged, target):
    """Pack the staged deck, then copy it to target in one write"""
    packed = staged.folder / _PACKED
    pack_container(staged.deck, packed)
    target = Path(target)
    try:
        with open(packed, "rb") as source, open(target, "wb") as out:
            shutil.copyfileobj(source, out)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def discard(staged):
    shutil.rmtree(staged.folder, ignore_errors=True)


def suggested_name(name, version):
    stem = deck_writer.slug(name) or "deck"
    return f"{stem}-{version}{CONTAINER_SUFFIX}" if version else f"{stem}{CONTAINER_SUFFIX}"


def with_suffix(path):
    """path, with .tarotdeck added if it has no suffix"""
    path = Path(path)
    return path if path.suffix else path.with_name(path.name + CONTAINER_SUFFIX)
