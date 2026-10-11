"""Every font the app sets, chosen by role from the platform's.

The platform supplies the body font and the app only derives from it, as ui/palette.py does
for colours. This is the only module that sets a font's size or family. A widget given a
role with apply() follows the application font when it changes; painted text calls font()
at paint time and needs no binding.
"""

import enum

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QFont, QFontDatabase, QFontInfo
from PyQt6.QtWidgets import QApplication


class Role(enum.Enum):
    BODY = "body"
    SMALL = "small"
    HEADING_1 = "heading_1"
    HEADING_2 = "heading_2"
    HEADING_3 = "heading_3"
    HEADING_4 = "heading_4"


# Kirigami's Heading levels 1-4, as multiples of the body font
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
    # A pixel-sized font has no point size, so compare what each resolves to
    small = QFontDatabase.systemFont(QFontDatabase.SystemFont.SmallestReadableFont)
    if QFontInfo(small).pointSizeF() < QFontInfo(body).pointSizeF():
        return small
    return _scaled(body, SMALL_FALLBACK_SCALE)


def font(role, *, primary=False, fixed=False):
    """A fresh font for `role`, derived from the application font as it is now"""
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
    return result


def _encode(role, primary, fixed):
    return ",".join([role.value] + ["primary"] * primary + ["fixed"] * fixed)


def _decode(value):
    role, *options = value.split(",")
    return Role(role), "primary" in options, "fixed" in options


def apply(widget, role, *, primary=False, fixed=False):
    """Set `widget` in `role`'s font, and keep it there when the application font changes"""
    widget.setProperty(PROPERTY, _encode(role, primary, fixed))
    widget.setFont(font(role, primary=primary, fixed=fixed))
    return widget


def _reapply(widget):
    value = widget.property(PROPERTY)
    if not value:
        return False
    role, primary, fixed = _decode(value)
    widget.setFont(font(role, primary=primary, fixed=fixed))
    widget.updateGeometry()
    return True


def reapply_all():
    """Re-derive every widget given a role, such as after a size the app scales by changes"""
    for widget in QApplication.allWidgets():
        _reapply(widget)


class _FontChangeFilter(QObject):
    def eventFilter(self, watched, event):
        # Qt sends the change to the application first, and on to widgets only when no
        # style sheet is set. The theme sets one, so re-apply every role from here.
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
