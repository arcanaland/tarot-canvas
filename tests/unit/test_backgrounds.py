import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QImage

from tarot_canvas.models import backgrounds
from tarot_canvas.settings import (
    BACKGROUND_POSITIONING_DEFAULT,
    BACKGROUND_POSITIONING_KEY,
    get_background_positioning,
    get_settings,
)


def write_image(path, colour="#c03030"):
    image = QImage(QSize(40, 20), QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    path.parent.mkdir(parents=True, exist_ok=True)
    assert image.save(str(path))
    return path


def test_adding_an_image_copies_it_in(qapp, tmp_path, backgrounds_base):
    source = write_image(tmp_path / "picked" / "felt.png")

    name = backgrounds.add_background(source)

    assert name == "felt.png"
    assert (backgrounds_base / name).read_bytes() == source.read_bytes()
    assert source.exists()
    assert backgrounds.list_backgrounds() == ["felt.png"]


def test_the_same_file_twice_is_one_copy(qapp, tmp_path, backgrounds_base):
    source = write_image(tmp_path / "felt.png")

    assert backgrounds.add_background(source) == backgrounds.add_background(source)
    assert backgrounds.list_backgrounds() == ["felt.png"]


def test_a_different_file_of_the_same_name_gets_a_free_name(qapp, tmp_path, backgrounds_base):
    first = write_image(tmp_path / "a" / "felt.png", "#102030")
    second = write_image(tmp_path / "b" / "felt.png", "#302010")

    assert backgrounds.add_background(first) == "felt.png"
    assert backgrounds.add_background(second) == "felt-2.png"
    assert backgrounds.list_backgrounds() == ["felt-2.png", "felt.png"]


def test_a_file_that_isnt_an_image_is_not_added(qapp, tmp_path, backgrounds_base):
    source = tmp_path / "notes.png"
    source.write_text("not an image")

    assert backgrounds.add_background(source) is None
    assert not backgrounds_base.exists() or not any(backgrounds_base.iterdir())


def test_the_list_holds_images_only(qapp, tmp_path, backgrounds_base):
    write_image(backgrounds_base / "wood.jpg")
    (backgrounds_base / "wood.jpg.part").write_bytes(b"")
    (backgrounds_base / "readme.txt").write_text("")
    (backgrounds_base / "dir.png").mkdir()

    assert backgrounds.list_backgrounds() == ["wood.jpg"]


@pytest.mark.parametrize("name", ["", ".", "..", "../felt.png", "sub/felt.png"])
def test_only_a_bare_file_name_names_a_copy(backgrounds_base, name):
    assert backgrounds.background_path(name) is None


def test_removing_deletes_the_copy(qapp, backgrounds_base):
    write_image(backgrounds_base / "felt.png")

    backgrounds.remove_background("felt.png")
    backgrounds.remove_background("felt.png")

    assert backgrounds.list_backgrounds() == []


def test_an_unknown_positioning_reads_as_the_default():
    settings = get_settings()
    settings.setValue(BACKGROUND_POSITIONING_KEY, "sideways")
    assert get_background_positioning(settings) == BACKGROUND_POSITIONING_DEFAULT
    settings.setValue(BACKGROUND_POSITIONING_KEY, "tile")
    assert get_background_positioning(settings) == "tile"
