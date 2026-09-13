"""TODO: delete when we replace the container stuff with libarcana"""

import stat
import struct
import zipfile

import pytest

from tarot_canvas.models.deck_container import (
    ContainerError,
    Limits,
    Reason,
    unpack_container,
)

DECK_TOML = b'[deck]\nschema_version = "2.0"\nname = "Test"\nversion = "1.0"\n'
MIME = b"application/vnd.arcana-land.tarotdeck+zip"


def build(tmp_path, entries, mimetype=True, name="deck.tarotdeck"):
    """A container from (name_or_ZipInfo, data[, compress_type]) entries."""
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        if mimetype:
            archive.writestr("mimetype", MIME, compress_type=zipfile.ZIP_STORED)
        for entry in entries:
            archive.writestr(*entry)
    return path


def conformant(tmp_path, mimetype=True, extra=()):
    return build(
        tmp_path,
        [
            ("deck.toml", DECK_TOML),
            ("h1200/", b""),
            ("h1200/major_arcana/00.png", b"\x89PNG fool"),
            ("names/en.toml", b"[name]\n"),
            *extra,
        ],
        mimetype=mimetype,
    )


def patch_central(path, entry_name, offset, fmt, value):
    """Rewrite one field of an entry's central-directory header."""
    data = bytearray(path.read_bytes())
    i = data.find(b"PK\x01\x02")
    while i != -1:
        name_len = struct.unpack_from("<H", data, i + 28)[0]
        if data[i + 46 : i + 46 + name_len] == entry_name:
            struct.pack_into(fmt, data, i + offset, value)
        i = data.find(b"PK\x01\x02", i + 4)
    path.write_bytes(bytes(data))


@pytest.fixture
def dest(tmp_path):
    """An empty destination inside a parent nothing else writes to."""
    d = tmp_path / "parent" / "dest"
    d.mkdir(parents=True)
    return d


def rejects(container, dest, reason, **kwargs):
    with pytest.raises(ContainerError) as caught:
        unpack_container(container, dest, **kwargs)
    assert caught.value.reason == reason, caught.value
    assert [p.name for p in dest.parent.iterdir()] == ["dest"]
    return caught.value


def tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


# --- acceptance ---------------------------------------------------------------


@pytest.mark.parametrize("mimetype", [True, False], ids=["with-mimetype", "without-mimetype"])
def test_a_conformant_container_unpacks_to_its_tree(tmp_path, dest, mimetype):
    unpack_container(conformant(tmp_path, mimetype=mimetype), dest)

    expected = ["deck.toml", "h1200", "h1200/major_arcana", "h1200/major_arcana/00.png"]
    expected += ["names", "names/en.toml"]
    assert tree(dest) == sorted(expected)
    assert (dest / "deck.toml").read_bytes() == DECK_TOML
    assert (dest / "h1200/major_arcana/00.png").read_bytes() == b"\x89PNG fool"
    assert [p.name for p in dest.parent.iterdir()] == ["dest"]


def test_the_root_mimetype_entry_is_not_unpacked(tmp_path, dest):
    unpack_container(conformant(tmp_path), dest)
    assert not (dest / "mimetype").exists()


def test_a_nested_mimetype_is_deck_material_and_is_unpacked(tmp_path, dest):
    unpack_container(conformant(tmp_path, extra=[("src/mimetype", b"mine")]), dest)
    assert (dest / "src/mimetype").read_bytes() == b"mine"


def test_a_utf8_flagged_name_is_accepted(tmp_path, dest):
    unpack_container(conformant(tmp_path, extra=[("names/café.toml", b"")]), dest)
    assert (dest / "names" / "café.toml").exists()


def test_dest_must_be_empty(tmp_path, dest):
    (dest / "stray").touch()
    with pytest.raises(ValueError):
        unpack_container(conformant(tmp_path), dest)


# --- the archive --------------------------------------------------------------


def test_not_a_zip(tmp_path, dest):
    path = tmp_path / "deck.tarotdeck"
    path.write_bytes(b"not a zip at all")
    rejects(path, dest, Reason.NOT_A_ZIP)


def test_no_deck_toml_at_the_root(tmp_path, dest):
    rejects(build(tmp_path, [("h1200/x.png", b"x")]), dest, Reason.NO_DECK_TOML)


def test_a_deck_toml_directory_is_not_a_deck_toml(tmp_path, dest):
    rejects(build(tmp_path, [("deck.toml/", b"")]), dest, Reason.NO_DECK_TOML)


def test_a_wrapping_directory_is_named_as_such(tmp_path, dest):
    """Every old reference-decks .zip has this shape."""
    container = build(
        tmp_path,
        [("aquatic-tarot/deck.toml", DECK_TOML), ("aquatic-tarot/h800/00.jpg", b"x")],
        mimetype=False,
    )
    error = rejects(container, dest, Reason.WRAPPED)
    assert error.detail == "aquatic-tarot"


def test_two_top_level_directories_are_not_a_wrapper(tmp_path, dest):
    container = build(tmp_path, [("a/deck.toml", DECK_TOML), ("b/deck.toml", DECK_TOML)])
    rejects(container, dest, Reason.NO_DECK_TOML)


# --- entry names --------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "/etc/passwd",
        "C:/deck/x.png",
        "c:x.png",
        "h1200\\00.png",
        "../escape.png",
        "h1200/../../escape.png",
        "h1200/./00.png",
        "h1200//00.png",
        "./00.png",
        "h1200/..",
        "dir//",
    ],
)
def test_unsafe_names_are_rejected_not_repaired(tmp_path, dest, name):
    container = conformant(tmp_path, extra=[(zipfile.ZipInfo(name), b"x")])
    rejects(container, dest, Reason.UNSAFE_NAME)


def test_a_nul_in_a_name_is_rejected(tmp_path, dest):
    container = conformant(tmp_path, extra=[("h1200/aa.png", b"x")])
    data = container.read_bytes().replace(b"h1200/aa.png", b"h1200/a\0.png")
    container.write_bytes(data)
    rejects(container, dest, Reason.UNSAFE_NAME)


def test_a_single_trailing_slash_marks_a_directory(tmp_path, dest):
    unpack_container(conformant(tmp_path, extra=[("empty/", b"")]), dest)
    assert (dest / "empty").is_dir()


def test_duplicate_names_are_rejected(tmp_path, dest):
    container = conformant(tmp_path)
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(container, "a") as archive,
    ):
        archive.writestr("deck.toml", b"[deck]\nname = 'second'\n")
    rejects(container, dest, Reason.DUPLICATE_NAME)


def test_a_file_and_a_directory_of_one_name_are_duplicates(tmp_path, dest):
    container = conformant(tmp_path, extra=[("names/en.toml/", b"")])
    rejects(container, dest, Reason.DUPLICATE_NAME)


def test_a_file_cannot_also_be_a_parent(tmp_path, dest):
    container = conformant(tmp_path, extra=[("names/en.toml/inner", b"x")])
    rejects(container, dest, Reason.DUPLICATE_NAME)


def test_a_non_utf8_name_is_rejected(tmp_path, dest):
    """Flag bit 11 unset and a byte outside ASCII: CP437 by the ZIP spec, not UTF-8."""
    container = conformant(tmp_path, extra=[("names/caf_.toml", b"")])
    data = container.read_bytes().replace(b"names/caf_.toml", b"names/caf\xe9.toml")
    container.write_bytes(data)
    rejects(container, dest, Reason.NON_UTF8_NAME)


def test_a_utf8_flagged_name_that_is_not_utf8_is_rejected(tmp_path, dest):
    container = conformant(tmp_path, extra=[("names/caf\u00e9.toml", b"")])
    data = container.read_bytes().replace("caf\u00e9".encode(), b"caf\xff\xfe")
    container.write_bytes(data)
    rejects(container, dest, Reason.NON_UTF8_NAME)


# --- entry types --------------------------------------------------------------


def unix_entry(name, mode):
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = mode << 16
    return info


def test_a_symlink_is_rejected(tmp_path, dest):
    link = unix_entry("h1200/00.png", stat.S_IFLNK | 0o777)
    rejects(conformant(tmp_path, extra=[(link, b"../../deck.toml")]), dest, Reason.NOT_REGULAR)


@pytest.mark.parametrize("kind", [stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK])
def test_special_files_are_rejected(tmp_path, dest, kind):
    special = unix_entry("special", kind | 0o644)
    rejects(conformant(tmp_path, extra=[(special, b"")]), dest, Reason.NOT_REGULAR)


def test_unix_regular_files_and_directories_are_fine(tmp_path, dest):
    extra = [
        (unix_entry("plain.txt", stat.S_IFREG | 0o644), b"x"),
        (unix_entry("sub/", stat.S_IFDIR | 0o755), b""),
    ]
    unpack_container(conformant(tmp_path, extra=extra), dest)
    assert (dest / "plain.txt").is_file() and (dest / "sub").is_dir()


def test_an_encrypted_entry_is_rejected(tmp_path, dest):
    container = conformant(tmp_path, extra=[("secret.png", b"x")])
    patch_central(container, b"secret.png", 8, "<H", 0x1)
    rejects(container, dest, Reason.ENCRYPTED)


def test_bzip2_is_not_stored_or_deflate(tmp_path, dest):
    container = conformant(tmp_path, extra=[("h1200/01.png", b"x" * 100, zipfile.ZIP_BZIP2)])
    rejects(container, dest, Reason.COMPRESSION)


# --- bounds -------------------------------------------------------------------


def test_a_101_to_1_entry_is_rejected(tmp_path, dest):
    container = conformant(tmp_path, extra=[("zeros.bin", bytes(4 * 1024 * 1024))])
    rejects(container, dest, Reason.RATIO)


def test_too_many_entries(tmp_path, dest):
    limits = Limits(max_total_size=1 << 20, max_entries=3, max_ratio=100)
    rejects(conformant(tmp_path), dest, Reason.TOO_MANY_ENTRIES, limits=limits)


def test_too_large_in_total(tmp_path, dest):
    limits = Limits(max_total_size=64, max_entries=100, max_ratio=100)
    rejects(conformant(tmp_path), dest, Reason.TOO_LARGE, limits=limits)


def test_a_header_that_overstates_its_size_is_caught_while_copying(tmp_path, dest):
    container = conformant(tmp_path, extra=[("h1200/01.png", b"A" * 1000, zipfile.ZIP_STORED)])
    patch_central(container, b"h1200/01.png", 24, "<I", 2000)
    with pytest.raises(ContainerError) as caught:
        unpack_container(container, dest)
    assert caught.value.reason == Reason.SIZE_MISMATCH


def test_a_header_that_understates_its_size_is_caught_while_copying(tmp_path, dest):
    """zipfile stops at the header's size, so the CRC no longer matches."""
    container = conformant(tmp_path, extra=[("h1200/01.png", b"A" * 1000)])
    patch_central(container, b"h1200/01.png", 24, "<I", 10)
    with pytest.raises(ContainerError) as caught:
        unpack_container(container, dest)
    assert caught.value.reason == Reason.CORRUPT
    assert (dest / "h1200/01.png").stat().st_size <= 10


def test_nothing_is_written_when_a_header_breaks_a_rule(tmp_path, dest):
    """Checks run before extraction, so a bad last entry leaves dest empty."""
    container = conformant(tmp_path, extra=[("../escape.png", b"x")])
    rejects(container, dest, Reason.UNSAFE_NAME)
    assert list(dest.iterdir()) == []
