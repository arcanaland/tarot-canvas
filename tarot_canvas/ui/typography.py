import enum

from PyQt6.QtCore import QEvent, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase, QFontInfo
from PyQt6.QtWidgets import QApplication

from tarot_canvas.settings import (
    READING_TEXT_SCALE_DEFAULT,
    READING_TEXT_SCALE_KEY,
    READING_TEXT_SCALE_STEPS,
    get_reading_text_scale,
    get_settings,
    snap_reading_text_scale,
)


class Role(enum.Enum):
    BODY = "body"
    SMALL = "small"
    HEADING_1 = "heading_1"
    HEADING_2 = "heading_2"
    HEADING_3 = "heading_3"
    HEADING_4 = "heading_4"


HEADING_SCALES = {
    Role.HEADING_1: 1.35,
    Role.HEADING_2: 1.20,
    Role.HEADING_3: 1.15,
    Role.HEADING_4: 1.10,
}

# Small text where the platform reports no smaller font than the body
SMALL_FALLBACK_SCALE = 0.85

PROPERTY = "typography"


def _scaled(base, scale):
    """A copy of `base` at `scale` times its size, in whatever unit it uses"""
    font = QFont(base)
    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() * scale)
    else:
        font.setPixelSize(max(1, round(font.pixelSize() * scale)))
    return font


def _sized_like(font, base):
    """`font` at `base`'s size, in `base`'s unit"""
    font = QFont(font)
    if base.pointSizeF() > 0:
        font.setPointSizeF(base.pointSizeF())
    else:
        font.setPixelSize(base.pixelSize())
    return font


def _small(body):
    small = QFontDatabase.systemFont(QFontDatabase.SystemFont.SmallestReadableFont)
    if QFontInfo(small).pointSizeF() < QFontInfo(body).pointSizeF():
        return small
    return _scaled(body, SMALL_FALLBACK_SCALE)


def font(role, *, primary=False, fixed=False, reading=False):
    """A fresh font for `role`, derived from the application font as it is now.

    Reading text is further scaled by the reading size the user chose.
    """
    body = QApplication.font()
    if role is Role.BODY:
        result = QFont(body)
    elif role is Role.SMALL:
        result = _small(body)
    else:
        result = _scaled(body, HEADING_SCALES[role])
        result.setWeight(QFont.Weight.Normal)
    if primary:
        result.setWeight(QFont.Weight.DemiBold)
    if fixed:
        monospace = _sized_like(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont), result
        )
        monospace.setWeight(result.weight())
        result = monospace
    if reading:
        scale = get_reading_text_scale()
        if scale != READING_TEXT_SCALE_DEFAULT:
            result = _scaled(result, scale / 100)
    return result


def _encode(role, primary, fixed, reading):
    options = ["primary"] * primary + ["fixed"] * fixed + ["reading"] * reading
    return ",".join([role.value, *options])


def _decode(value):
    role, *options = value.split(",")
    return Role(role), {option: True for option in options}


def apply(widget, role, *, primary=False, fixed=False, reading=False):
    """Set `widget` in `role`'s font, and keep it there when the application font or the
    reading size changes"""
    widget.setProperty(PROPERTY, _encode(role, primary, fixed, reading))
    widget.setFont(font(role, primary=primary, fixed=fixed, reading=reading))
    return widget


def _reapply(widget):
    value = widget.property(PROPERTY)
    if not value:
        return False
    role, options = _decode(value)
    widget.setFont(font(role, **options))
    widget.updateGeometry()
    return True


def reapply_all():
    """Re-derive every widget given a role, such as after a size the app scales by changes"""
    for widget in QApplication.allWidgets():
        _reapply(widget)


class TypographyEvents(QObject):
    # The reading size changed, to this percentage
    reading_scale_changed = pyqtSignal(int)


_events = None


def events():
    global _events
    if _events is None:
        _events = TypographyEvents()
    return _events


def reading_scale():
    """The reading size, as a percentage of the system's"""
    return get_reading_text_scale()


def set_reading_scale(percent):
    """Store the reading size and resize every reading surface to it. The only way it changes."""
    percent = snap_reading_text_scale(percent)
    if percent == reading_scale():
        return
    get_settings().setValue(READING_TEXT_SCALE_KEY, percent)
    reapply_all()
    events().reading_scale_changed.emit(percent)


def zoom_in():
    """One step larger, up to the largest"""
    larger = [step for step in READING_TEXT_SCALE_STEPS if step > reading_scale()]
    if larger:
        set_reading_scale(larger[0])


def zoom_out():
    """One step smaller, down to the smallest"""
    smaller = [step for step in READING_TEXT_SCALE_STEPS if step < reading_scale()]
    if smaller:
        set_reading_scale(smaller[-1])


def reset_zoom():
    set_reading_scale(READING_TEXT_SCALE_DEFAULT)


class _FontChangeFilter(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.ApplicationFontChange and watched is QApplication.instance():
            reapply_all()
        return False


_filter = None


def install(app):
    """Re-apply each widget's role when the application font changes.

    Plasma calls QApplication.setFont when the user changes the system font. A role's font
    sets its size explicitly, so without this it would keep the old one.
    """
    global _filter
    if _filter is None:
        _filter = _FontChangeFilter(app)
        app.installEventFilter(_filter)
    return _filter


def uninstall(app):
    global _filter
    if _filter is not None:
        app.removeEventFilter(_filter)
        _filter = None
