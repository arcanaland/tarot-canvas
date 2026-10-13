import pytest
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from tarot_canvas.settings import (
    READING_TEXT_SCALE_KEY,
    READING_TEXT_SCALE_STEPS,
    get_reading_text_scale,
    get_settings,
    snap_reading_text_scale,
)
from tarot_canvas.ui import typography
from tarot_canvas.ui.typography import Role


def size(font):
    return font.pointSizeF() if font.pointSizeF() > 0 else font.pixelSize()


@pytest.fixture
def body(qapp):
    """A known application font, restored afterwards"""
    saved = QApplication.font()
    font = QFont(saved)
    font.setPointSizeF(10)
    QApplication.setFont(font)
    yield font
    QApplication.setFont(saved)


def test_nothing_stored_is_100():
    assert get_reading_text_scale() == 100


@pytest.mark.parametrize(
    ("stored", "snapped"),
    [
        (150, 150),
        ("125", 125),
        (95, 100),  # a tie goes up
        (93, 90),
        (130, 125),
        (10, 80),
        (1000, 200),
        ("large", 100),
        (None, 100),
        ("nan", 100),
    ],
)
def test_a_stored_value_snaps_to_the_nearest_step(stored, snapped):
    get_settings().setValue(READING_TEXT_SCALE_KEY, stored)
    assert get_reading_text_scale() == snapped


def test_setting_it_snaps_and_persists():
    typography.set_reading_scale(140)

    assert get_settings().value(READING_TEXT_SCALE_KEY, type=int) == 150
    assert typography.reading_scale() == 150


def test_setting_it_says_so(qtbot):
    with qtbot.waitSignal(typography.events().reading_scale_changed) as blocker:
        typography.set_reading_scale(125)
    assert blocker.args == [125]


def test_setting_the_same_size_says_nothing(qtbot):
    typography.set_reading_scale(125)
    with qtbot.assertNotEmitted(typography.events().reading_scale_changed):
        typography.set_reading_scale(125)


def test_zoom_steps_through_every_size_and_stops_at_the_ends():
    seen = [typography.reading_scale()]
    for _ in READING_TEXT_SCALE_STEPS:
        typography.zoom_in()
        seen.append(typography.reading_scale())
    assert seen[-2:] == [200, 200]

    for _ in READING_TEXT_SCALE_STEPS:
        typography.zoom_out()
    assert typography.reading_scale() == 80
    typography.zoom_out()
    assert typography.reading_scale() == 80

    assert sorted(set(seen)) == [step for step in READING_TEXT_SCALE_STEPS if step >= 100]


def test_reset_is_100():
    typography.set_reading_scale(175)
    typography.reset_zoom()
    assert typography.reading_scale() == 100


def test_snapping_is_exposed_for_the_dialog():
    assert snap_reading_text_scale(112) == 110


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("fixed", [False, True])
def test_reading_multiplies_every_role(body, role, fixed):
    plain = typography.font(role, fixed=fixed)
    typography.set_reading_scale(150)

    reading = typography.font(role, fixed=fixed, reading=True)

    assert size(reading) == pytest.approx(size(plain) * 1.5, abs=0.5)
    assert size(typography.font(role, fixed=fixed)) == size(plain)


def test_a_reading_widget_follows_the_scale_and_a_chrome_one_does_not(qtbot, body):
    reading = typography.apply(QLabel(), Role.BODY, reading=True)
    chrome = typography.apply(QLabel(), Role.BODY)
    for widget in (reading, chrome):
        qtbot.addWidget(widget)

    typography.set_reading_scale(200)

    assert size(reading.font()) == pytest.approx(2 * size(chrome.font()), abs=0.5)


def test_text_under_a_reading_container_scales_with_it_but_keeps_its_style(qtbot, body):
    """Prose rows set italic or bold on themselves and take their size from the passages"""
    container = typography.apply(QWidget(), Role.BODY, reading=True)
    qtbot.addWidget(container)
    italic = QLabel()
    font = italic.font()
    font.setItalic(True)
    italic.setFont(font)
    italic.setParent(container)
    plain = QLabel(container)

    typography.set_reading_scale(150)

    assert size(plain.font()) == pytest.approx(15, abs=0.5)
    assert size(italic.font()) == pytest.approx(15, abs=0.5)
    assert italic.font().italic()
