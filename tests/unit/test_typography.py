import pytest
from PyQt6.QtGui import QFont, QFontDatabase, QFontInfo
from PyQt6.QtWidgets import QApplication

from tarot_canvas.ui import typography
from tarot_canvas.ui.typography import HEADING_SCALES, SMALL_FALLBACK_SCALE, Role


def body_font(unit):
    font = QFont(QApplication.font())
    if unit == "points":
        font.setPointSizeF(10)
    else:
        font.setPixelSize(14)
    return font


def size(font):
    return font.pointSizeF() if font.pointSizeF() > 0 else font.pixelSize()


@pytest.fixture(params=["points", "pixels"])
def body(request, qapp):
    """A known application font, in either unit, restored afterwards"""
    saved = QApplication.font()
    font = body_font(request.param)
    QApplication.setFont(font)
    yield font
    QApplication.setFont(saved)


def test_body_is_the_application_font(body):
    assert typography.font(Role.BODY) == QApplication.font()


@pytest.mark.parametrize("role", list(HEADING_SCALES))
def test_a_heading_is_the_body_at_its_level(body, role):
    heading = typography.font(role)

    assert heading.family() == body.family()
    assert size(heading) == pytest.approx(size(body) * HEADING_SCALES[role], abs=0.5)


def test_the_heading_levels_shrink_in_order(body):
    sizes = [size(typography.font(role)) for role in HEADING_SCALES]
    assert sizes == sorted(sizes, reverse=True)


@pytest.mark.parametrize("role", list(HEADING_SCALES))
def test_a_heading_is_normal_and_a_primary_one_demibold(body, role):
    assert typography.font(role).weight() == QFont.Weight.Normal
    assert typography.font(role, primary=True).weight() == QFont.Weight.DemiBold


def test_small_is_smaller_than_body(body):
    assert QFontInfo(typography.font(Role.SMALL)).pointSizeF() < QFontInfo(body).pointSizeF()


def test_small_falls_back_to_a_fraction_of_body(body, monkeypatch):
    # A platform whose smallest readable font is no smaller than the body
    monkeypatch.setattr(typography.QFontDatabase, "systemFont", staticmethod(lambda _: QFont(body)))

    small = typography.font(Role.SMALL)

    assert small.family() == body.family()
    assert size(small) == pytest.approx(size(body) * SMALL_FALLBACK_SCALE, abs=0.5)


def test_small_takes_the_platform_font_when_it_is_smaller(body, monkeypatch):
    platform_small = QFont(body)
    platform_small.setFamily("Platform Small")
    platform_small.setPointSizeF(QFontInfo(body).pointSizeF() / 2)
    monkeypatch.setattr(
        typography.QFontDatabase, "systemFont", staticmethod(lambda _: QFont(platform_small))
    )

    assert typography.font(Role.SMALL).family() == "Platform Small"


@pytest.mark.parametrize("role", [Role.BODY, Role.SMALL, Role.HEADING_2])
def test_fixed_is_the_fixed_family_at_the_role_size(body, role):
    fixed = typography.font(role, fixed=True)
    system_fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)

    assert fixed.family() == system_fixed.family()
    assert size(fixed) == size(typography.font(role))


def test_each_call_is_a_fresh_font(body):
    first = typography.font(Role.BODY)
    first.setItalic(True)
    assert not typography.font(Role.BODY).italic()
