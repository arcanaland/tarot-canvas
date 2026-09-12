"""Unpack a zipped deck container

TODO: This will eventually be replaced by libarcana.
"""

import enum
import re
import stat
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

DECK_TOML = "deck.toml"
MIMETYPE = "mimetype"

_UTF8_NAME_FLAG = 0x800
_ENCRYPTED_FLAG = 0x1
_UNIX = 3
_DRIVE = re.compile(r"^[A-Za-z]:")
_CHUNK = 1 << 16


class Reason(enum.Enum):
    NOT_A_ZIP = "not a zip archive"
    CORRUPT = "corrupt archive"
    UNSAFE_NAME = "unsafe entry name"
    NON_UTF8_NAME = "entry name not UTF-8"
    DUPLICATE_NAME = "duplicate entry name"
    NOT_REGULAR = "link or special file"
    ENCRYPTED = "encrypted entry"
    COMPRESSION = "unsupported compression"
    TOO_MANY_ENTRIES = "too many entries"
    TOO_LARGE = "too large uncompressed"
    RATIO = "compression ratio too high"
    SIZE_MISMATCH = "entry size differs from its header"
    NO_DECK_TOML = "no deck.toml at the archive root"
    WRAPPED = "deck inside a wrapping directory"
    INVALID_DECK_TOML = "deck.toml is not valid TOML"


class ContainerError(Exception):
    def __init__(self, reason, detail=""):
        super().__init__(f"{reason.value}: {detail}" if detail else reason.value)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Limits:
    max_total_size: int
    max_entries: int
    max_ratio: int


DEFAULT_LIMITS = Limits(max_total_size=2 * 1024**3, max_entries=20_000, max_ratio=100)


def unpack_container(container_path, dest_dir, limits=DEFAULT_LIMITS):
    """Unpack the container into dest_dir which must exist and be empty."""
    dest_dir = Path(dest_dir)
    if not dest_dir.is_dir() or any(dest_dir.iterdir()):
        raise ValueError(f"{dest_dir} is not an empty directory")

    try:
        archive = zipfile.ZipFile(container_path)
    except UnicodeDecodeError as e:
        raise ContainerError(Reason.NON_UTF8_NAME, str(e)) from e
    except (zipfile.BadZipFile, EOFError, ValueError) as e:
        raise ContainerError(Reason.NOT_A_ZIP, str(e)) from e

    with archive:
        infos = archive.infolist()
        _check_entries(infos, limits)
        try:
            _extract(archive, infos, dest_dir, limits)
        except (zipfile.BadZipFile, EOFError, zlib.error) as e:
            raise ContainerError(Reason.CORRUPT, str(e)) from e


def _check_entries(infos, limits):
    if len(infos) > limits.max_entries:
        raise ContainerError(Reason.TOO_MANY_ENTRIES, str(len(infos)))

    files, dirs = set(), set()
    for info in infos:
        name = info.orig_filename
        _check_name(info, name)
        _check_type(info, name)

        is_dir = name.endswith("/")
        path = name[:-1] if is_dir else name
        if path in files or path in dirs:
            raise ContainerError(Reason.DUPLICATE_NAME, name)
        (dirs if is_dir else files).add(path)

    # A file whose name is also another entry's parent can't be extracted.
    for path in files | dirs:
        parts = path.split("/")
        for i in range(1, len(parts)):
            parent = "/".join(parts[:i])
            if parent in files:
                raise ContainerError(Reason.DUPLICATE_NAME, f"{parent} is a file and a directory")

    _check_root(files)
    _check_sizes(infos, limits)


def _check_name(info, name):
    if not name.isascii() and not info.flag_bits & _UTF8_NAME_FLAG:
        raise ContainerError(Reason.NON_UTF8_NAME, name)
    if not name or name.startswith("/") or "\\" in name or "\0" in name or _DRIVE.match(name):
        raise ContainerError(Reason.UNSAFE_NAME, repr(name))
    body = name[:-1] if name.endswith("/") else name
    if any(segment in ("", ".", "..") for segment in body.split("/")):
        raise ContainerError(Reason.UNSAFE_NAME, repr(name))


def _check_type(info, name):
    if info.create_system == _UNIX:
        mode = info.external_attr >> 16
        if stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ContainerError(Reason.NOT_REGULAR, name)
    if info.flag_bits & _ENCRYPTED_FLAG:
        raise ContainerError(Reason.ENCRYPTED, name)
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise ContainerError(Reason.COMPRESSION, f"{name}: method {info.compress_type}")


def _check_root(files):
    if DECK_TOML in files:
        return
    tops = {path.split("/", 1)[0] for path in files if path != MIMETYPE}
    if len(tops) == 1 and f"{next(iter(tops))}/{DECK_TOML}" in files:
        raise ContainerError(Reason.WRAPPED, next(iter(tops)))
    raise ContainerError(Reason.NO_DECK_TOML)


def _check_sizes(infos, limits):
    total = sum(info.file_size for info in infos)
    if total > limits.max_total_size:
        raise ContainerError(Reason.TOO_LARGE, f"{total} bytes")
    for info in infos:
        if _over_ratio(info.file_size, info.compress_size, limits):
            raise ContainerError(Reason.RATIO, info.orig_filename)
    if _over_ratio(total, sum(info.compress_size for info in infos), limits):
        raise ContainerError(Reason.RATIO, "whole archive")


def _over_ratio(size, compressed, limits):
    if compressed == 0:
        return size > 0
    return size > compressed * limits.max_ratio


def _extract(archive, infos, dest_dir, limits):
    written_total = 0
    for info in infos:
        name = info.orig_filename
        target = dest_dir.joinpath(*name.rstrip("/").split("/"))
        if name.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with archive.open(info) as src, open(target, "xb") as out:
            while chunk := src.read(_CHUNK):
                written += len(chunk)
                written_total += len(chunk)
                if written > info.file_size:
                    raise ContainerError(Reason.SIZE_MISMATCH, name)
                if written_total > limits.max_total_size:
                    raise ContainerError(Reason.TOO_LARGE, "while copying")
                out.write(chunk)
        if written != info.file_size:
            raise ContainerError(Reason.SIZE_MISMATCH, name)
