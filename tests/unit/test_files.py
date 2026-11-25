import os
import threading

import pytest

from tarot_canvas.utils.files import atomic_path, write_atomic

ROUNDS = 200


def test_two_writers_of_one_file_neither_fails_nor_tears_it(tmp_path):
    target = tmp_path / "marker.json"
    payloads = [b"a" * 65536, b"b" * 65536]
    barrier = threading.Barrier(len(payloads))
    errors = []

    def write(payload):
        barrier.wait()
        try:
            for _ in range(ROUNDS):
                write_atomic(target, payload)
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=write, args=(payload,)) for payload in payloads]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert target.read_bytes() in payloads
    assert os.listdir(tmp_path) == ["marker.json"]


def test_text_is_written_as_utf_8(tmp_path):
    target = tmp_path / "deck.toml"
    write_atomic(target, 'name = "Ŝtono"\n')
    assert target.read_bytes() == 'name = "Ŝtono"\n'.encode()


def test_a_failed_write_keeps_the_old_file_and_leaves_no_temporary(tmp_path):
    target = tmp_path / "library.toml"
    target.write_bytes(b"old")
    with pytest.raises(RuntimeError), atomic_path(target) as temporary:
        temporary.write_bytes(b"half")
        raise RuntimeError
    assert target.read_bytes() == b"old"
    assert os.listdir(tmp_path) == ["library.toml"]


def test_missing_folders_are_made(tmp_path):
    target = tmp_path / "cache" / "catalog" / "index.json"
    write_atomic(target, b"{}")
    assert target.read_bytes() == b"{}"
