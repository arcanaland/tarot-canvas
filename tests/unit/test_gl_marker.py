import json

import pytest

from tarot_canvas.ui.canvas.gl_marker import GlMarker, marker_key

FLATPAK_INFO = """[Application]
name=land.arcana.TarotCanvas

[Instance]
runtime-commit=fb23
runtime-extensions=org.kde.Platform.Locale=0372;org.freedesktop.Platform.GL.nvidia-580-95-05=9bb1;org.freedesktop.Platform.codecs-extra=4ac6;org.freedesktop.Platform.GL.default=c8dc
"""

KEY = ["1.8.0", "fb23", "k"]


def test_a_flatpak_key_holds_the_runtime_and_its_sorted_gl_extensions():
    assert marker_key("1.8.0", "6.11.0", "6.17.4", FLATPAK_INFO) == [
        "1.8.0",
        "fb23",
        "org.freedesktop.Platform.GL.default=c8dc",
        "org.freedesktop.Platform.GL.nvidia-580-95-05=9bb1",
        "6.17.4",
    ]


def test_a_source_key_holds_qt():
    assert marker_key("1.8.0", "6.11.0", "6.17.4", None) == ["1.8.0", "6.11.0", "6.17.4"]


def read(path):
    return json.loads(path.read_text())


@pytest.fixture
def path(tmp_path):
    return tmp_path / "gl-check.json"


def test_no_file_arms_the_probe(path):
    assert not GlMarker(path, KEY).failed()
    assert read(path) == {"key": KEY, "state": "trying", "stage": "probe"}


@pytest.mark.parametrize("state", ["trying", "failed"])
def test_the_same_key_failed(path, state):
    path.write_text(json.dumps({"key": KEY, "state": state, "stage": "window"}))

    assert GlMarker(path, KEY).failed()
    assert read(path) == {"key": KEY, "state": "failed", "stage": "window"}


@pytest.mark.parametrize("body", [json.dumps({"key": ["old"], "state": "failed"}), "{not json"])
def test_another_key_or_a_malformed_file_is_retried(path, body):
    path.write_text(body)

    assert not GlMarker(path, KEY).failed()
    assert read(path)["state"] == "trying"


def test_clear_without_a_file_does_nothing(path):
    GlMarker(path, KEY).clear()
    assert not path.exists()
