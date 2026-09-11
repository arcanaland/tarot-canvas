"""Install a deck container: unpack into staging, then rename into place.

A scan never sees a partly written deck, because the only write into a library
root is one `rename(2)`. Staging must be on the same filesystem as `dest` and
must not be a library root itself (the scanner lists dot-directories too).
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
    """The directory a deck installs as: the identifier's last segment, else `fallback`.

    `fallback` is the catalog's slug or the container's file stem (deck spec 2.4).
    """
    name = identifier.rsplit("/", 1)[-1] if identifier else fallback
    if not name or name in (".", "..") or any(c in name for c in ("/", "\\", "\0", os.sep)):
        raise ValueError(f"not a single path segment: {name!r}")
    return name


def install_container(container_path, dest, staging_root):
    """Unpack the container and rename it to `dest`, which must not exist.

    Raises ContainerError for a bad container and InstallError when it can't be
    placed; either way the staged copy is removed and `dest` is untouched.
    """
    dest = Path(dest)
    if os.path.lexists(dest):
        raise InstallError(InstallReason.DESTINATION_EXISTS, str(dest))

    staging_root = Path(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f"{dest.name}.", dir=staging_root))
    try:
        unpack_container(container_path, staged)
        _check_deck_toml(staged / DECK_TOML)
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
    # rename(2) silently replaces an *empty* directory; one that appeared since
    # the check above is the only case, and it held nothing to lose.
    try:
        os.rename(staged, dest)
    except OSError as e:
        if e.errno == errno.EXDEV:
            # Copying instead would be the non-atomic install this replaces.
            raise InstallError(InstallReason.FILESYSTEM, str(e)) from e
        if e.errno in (errno.EEXIST, errno.ENOTEMPTY, errno.ENOTDIR):
            raise InstallError(InstallReason.DESTINATION_EXISTS, str(dest)) from e
        raise
