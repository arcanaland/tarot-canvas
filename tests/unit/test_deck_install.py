import errno
import os
import zipfile
from pathlib import Path

import pytest

from tarot_canvas.models import deck_install
from tarot_canvas.models.deck_container import ContainerError, Reason
from tarot_canvas.models.deck_install import (
    InstallError,
    InstallReason,
    install_container,
    install_dir_name,
    install_local,
    open_local,
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
    from tarot_canvas.models.arcana_backend import load_deck

    root, staging = places
    dest = install_container(conformant(tmp_path), root / "test", staging)
    assert load_deck(str(dest)).metadata.name == "Test"


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


def exdev_from(staging, monkeypatch):
    """os.rename fails across devices for anything leaving staging"""
    rename = os.rename

    def maybe_exdev(src, dst):
        if Path(src).parent == staging:
            raise OSError(errno.EXDEV, os.strerror(errno.EXDEV))
        rename(src, dst)

    monkeypatch.setattr(deck_install.os, "rename", maybe_exdev)


def test_a_cross_device_rename_is_copied_then_renamed(tmp_path, places, monkeypatch):
    root, staging = places
    exdev_from(staging, monkeypatch)

    dest = install_container(conformant(tmp_path), root / "x", staging)

    assert (dest / "h1200/major_arcana/00.png").is_file()
    assert list(staging.iterdir()) == []
    assert [p.name for p in root.iterdir()] == ["x"]


def test_a_failed_cross_device_copy_leaves_nothing_behind(tmp_path, places, monkeypatch):
    root, staging = places
    exdev_from(staging, monkeypatch)

    def full(src, dst, **kwargs):
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(deck_install.shutil, "copytree", full)
    with pytest.raises(OSError):
        install_container(conformant(tmp_path), root / "x", staging)

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


def test_a_local_install_is_named_from_the_identifier(tmp_path, places):
    root, staging = places
    toml = b'[deck]\nschema_version = "2.0"\nname = "T"\nversion = "1"\nidentifier = "land.arcana.private/deck/mine-0a0a"\n'
    container = build(tmp_path, [("deck.toml", toml)], name="whatever.tarotdeck")

    assert install_local(container, root, staging) == root / "mine-0a0a"
    assert list(staging.iterdir()) == []


def test_a_local_install_without_an_identifier_takes_the_file_stem(tmp_path, places):
    root, staging = places
    container = conformant(tmp_path)

    assert install_local(container, root, staging) == root / "deck"


def test_a_second_local_install_is_refused(tmp_path, places):
    root, staging = places
    container = conformant(tmp_path)
    install_local(container, root, staging)
    before = snapshot(root)

    with pytest.raises(InstallError) as caught:
        install_local(container, root, staging)

    assert caught.value.reason is InstallReason.DESTINATION_EXISTS
    assert snapshot(root) == before
    assert list(staging.iterdir()) == []


def test_an_opened_container_is_unpacked_under_staging_and_not_installed(tmp_path, places):
    root, staging = places
    container = conformant(tmp_path)

    opened = open_local(container, staging)

    assert opened.parent == staging
    assert opened.name.startswith("deck.open.")
    assert (opened / "deck.toml").is_file()
    assert list(root.iterdir()) == []


def test_opening_a_rejected_container_leaves_nothing_behind(tmp_path, places):
    _root, staging = places
    container = build(tmp_path, [("deck.toml", b"not = [toml")])

    with pytest.raises(ContainerError):
        open_local(container, staging)

    assert list(staging.iterdir()) == []
