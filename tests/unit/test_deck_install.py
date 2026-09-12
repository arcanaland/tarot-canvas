import errno
import os
import zipfile

import pytest

from tarot_canvas.models import deck_install
from tarot_canvas.models.deck_container import ContainerError, Reason
from tarot_canvas.models.deck_install import (
    InstallError,
    InstallReason,
    install_container,
    install_dir_name,
)
from tests.unit.test_deck_container import build, conformant, patch_central


@pytest.fixture
def places(tmp_path):
    """(root, staging) side by side, as tarot/decks and tarot/.staging are."""
    root = tmp_path / "tarot" / "decks"
    root.mkdir(parents=True)
    return root, tmp_path / "tarot" / ".staging"


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_success_renames_into_dest(tmp_path, places):
    root, staging = places
    dest = root / "aquatic-tarot"

    assert install_container(conformant(tmp_path), dest, staging) == dest

    assert (dest / "deck.toml").is_file()
    assert (dest / "h1200/major_arcana/00.png").is_file()
    assert list(staging.iterdir()) == []


def test_the_installed_deck_loads(tmp_path, places):
    from tarot_canvas.models.deck import TarotDeck

    root, staging = places
    dest = install_container(conformant(tmp_path), root / "test", staging)
    assert TarotDeck(str(dest)).get_name() == "Test"


def test_an_existing_dest_is_never_touched(tmp_path, places):
    root, staging = places
    dest = root / "aquatic-tarot"
    dest.mkdir()
    (dest / "deck.toml").write_bytes(b"[deck]\nname = 'mine'\n")
    (dest / "art.png").write_bytes(b"keep me")
    before = snapshot(dest)

    with pytest.raises(InstallError) as caught:
        install_container(conformant(tmp_path), dest, staging)

    assert caught.value.reason == InstallReason.DESTINATION_EXISTS
    assert snapshot(dest) == before
    assert not staging.exists() or list(staging.iterdir()) == []


def test_an_existing_empty_dest_also_counts(tmp_path, places):
    root, staging = places
    (root / "empty").mkdir()
    with pytest.raises(InstallError):
        install_container(conformant(tmp_path), root / "empty", staging)


def test_a_rejected_container_leaves_nothing_behind(tmp_path, places):
    root, staging = places
    dest = root / "bad"
    # The oversized entry is found only while copying, after earlier files are written.
    container = conformant(tmp_path, extra=[("zzz.bin", b"A" * 1000, zipfile.ZIP_STORED)])
    patch_central(container, b"zzz.bin", 24, "<I", 2000)

    with pytest.raises(ContainerError):
        install_container(container, dest, staging)

    assert list(staging.iterdir()) == []
    assert not dest.exists()
    assert list(root.iterdir()) == []


def test_a_deck_toml_that_is_not_toml_is_rejected(tmp_path, places):
    root, staging = places
    container = build(tmp_path, [("deck.toml", b"[deck\nname = ")])

    with pytest.raises(ContainerError) as caught:
        install_container(container, root / "broken", staging)

    assert caught.value.reason == Reason.INVALID_DECK_TOML
    assert list(staging.iterdir()) == []
    assert list(root.iterdir()) == []


def test_a_cross_device_rename_is_not_copied(tmp_path, places, monkeypatch):
    root, staging = places

    def exdev(src, dst):
        raise OSError(errno.EXDEV, os.strerror(errno.EXDEV))

    monkeypatch.setattr(deck_install.os, "rename", exdev)
    with pytest.raises(InstallError) as caught:
        install_container(conformant(tmp_path), root / "x", staging)

    assert caught.value.reason == InstallReason.FILESYSTEM
    assert list(staging.iterdir()) == []
    assert list(root.iterdir()) == []


@pytest.mark.parametrize(
    ("identifier", "fallback", "expected"),
    [
        ("land.arcana/deck/ascii-tarot-lawreka", "ascii-tarot", "ascii-tarot-lawreka"),
        (None, "aquatic-tarot", "aquatic-tarot"),
        ("", "aquatic-tarot", "aquatic-tarot"),
        ("plain", "fallback", "plain"),
    ],
)
def test_install_dir_name(identifier, fallback, expected):
    assert install_dir_name(identifier, fallback) == expected


@pytest.mark.parametrize(
    ("identifier", "fallback"),
    [
        (None, ".."),
        (None, "."),
        (None, ""),
        (None, "a/b"),
        (None, "a\\b"),
        (None, "a\0b"),
        ("land.arcana/deck/..", "x"),
        ("land.arcana/deck/", "x"),
    ],
)
def test_install_dir_name_must_be_one_segment(identifier, fallback):
    with pytest.raises(ValueError):
        install_dir_name(identifier, fallback)
