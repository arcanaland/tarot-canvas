"""Install a deck container.

TODO: This will eventually be replaced by libarcana.
"""

import enum
import errno
import os
import shutil
import tempfile
import tomllib
from pathlib import Path

from tarot_canvas.models.deck_container import (
    DECK_TOML,
    ContainerError,
    Reason,
    unpack_container,
)


class InstallReason(enum.Enum):
    DESTINATION_EXISTS = "destination exists"
    FILESYSTEM = "staging and destination are on different filesystems"


class InstallError(Exception):
    def __init__(self, reason, detail=""):
        super().__init__(f"{reason.value}: {detail}" if detail else reason.value)
        self.reason = reason
        self.detail = detail


def install_dir_name(identifier, fallback):
    name = identifier.rsplit("/", 1)[-1] if identifier else fallback
    if not name or name in (".", "..") or any(c in name for c in ("/", "\\", "\0", os.sep)):
        raise ValueError(f"not a single path segment: {name!r}")
    return name


def install_container(container_path, dest, staging_root):
    """Unpack the container and rename it to dest."""
    dest = Path(dest)
    if os.path.lexists(dest):
        raise InstallError(InstallReason.DESTINATION_EXISTS, str(dest))
    return _install(container_path, staging_root, dest.name, lambda _staged: dest)


def install_local(container_path, decks_root, staging_root):
    """Unpack a container file into decks_root, named from its identifier, else its file name"""
    decks_root = Path(decks_root)

    def destination(staged):
        with open(staged / DECK_TOML, "rb") as f:
            table = tomllib.load(f).get("deck", {})
        identifier = table.get("identifier") if isinstance(table, dict) else None
        name = install_dir_name(
            identifier if isinstance(identifier, str) else None, Path(container_path).stem
        )
        dest = decks_root / name
        if os.path.lexists(dest):
            raise InstallError(InstallReason.DESTINATION_EXISTS, str(dest))
        return dest

    return _install(container_path, staging_root, Path(container_path).stem, destination)


def _install(container_path, staging_root, prefix, destination):
    """Unpack into staging, check deck.toml, then rename to destination(staged)"""
    staging_root = Path(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f"{prefix}.", dir=staging_root))
    try:
        unpack_container(container_path, staged)
        _check_deck_toml(staged / DECK_TOML)
        dest = destination(staged)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _rename(staged, dest)
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    return dest


def _check_deck_toml(path):
    try:
        with open(path, "rb") as f:
            tomllib.load(f)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise ContainerError(Reason.INVALID_DECK_TOML, str(e)) from e


def _rename(staged, dest):
    try:
        os.rename(staged, dest)
    except OSError as e:
        if e.errno == errno.EXDEV:
            _copy_across(staged, dest)
            return
        if e.errno in (errno.EEXIST, errno.ENOTEMPTY, errno.ENOTDIR):
            raise InstallError(InstallReason.DESTINATION_EXISTS, str(dest)) from e
        raise


def _copy_across(staged, dest):
    """Copy staged beside dest under a hidden name the library skips, then rename it into place"""
    partial = Path(tempfile.mkdtemp(prefix=f".{dest.name}.", suffix=".partial", dir=dest.parent))
    try:
        shutil.copytree(staged, partial, dirs_exist_ok=True)
        try:
            os.rename(partial, dest)
        except OSError as e:
            if e.errno in (errno.EEXIST, errno.ENOTEMPTY, errno.ENOTDIR):
                raise InstallError(InstallReason.DESTINATION_EXISTS, str(dest)) from e
            raise
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    shutil.rmtree(staged, ignore_errors=True)
