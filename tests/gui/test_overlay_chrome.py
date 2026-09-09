"""The chrome floating over the card image: painted, not stylesheet-ed.

Both overlays used to be QSS with literal black/white rgba(). That broke the
HIG twice over -- custom colours instead of the user's scheme
(hig/simple_by_default.md) -- and Qt draws a QSS `border-radius` as four edges
plus four corner arcs, so the translucent rim double-composited at each seam and
put bright pips on the curve.
"""

import math

import pytest
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

from tarot_canvas.ui.widgets.overlay_button import OverlayButton
from tarot_canvas.ui.widgets.overlay_chrome import fill_color, outline_color
from tarot_canvas.ui.widgets.toast import Toast


@pytest.fixture
def host(qtbot):
    widget = QWidget()
    widget.resize(400, 300)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


@pytest.fixture
def scheme():
    """Swap the application palette, and put the real one back afterwards."""
    app = QApplication.instance()
    original = app.palette()

    def apply(window, window_text):
        palette = QPalette(original)
        palette.setColor(QPalette.ColorRole.Window, QColor(window))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(window_text))
        app.setPalette(palette)

    yield apply
    app.setPalette(original)


def button(host, qtbot, row=0):
    widget = OverlayButton(host, "view-restore", "⛶", "Leave fullscreen", lambda: None, row=row)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def test_neither_overlay_carries_a_stylesheet(host, qtbot):
    assert button(host, qtbot).styleSheet() == ""
    assert Toast(host).styleSheet() == ""


def test_overlays_follow_the_colour_scheme(host, qtbot, scheme):
    """The HIG's § Color check: change the scheme, the chrome must change too."""
    scheme("#fcfcfc", "#232629")
    widget = button(host, qtbot)
    light = widget.grab().toImage()

    scheme("#31363b", "#fcfcfc")
    assert widget.grab().toImage() != light


def test_chrome_takes_the_window_scheme_not_the_view_palette(host, qtbot, scheme):
    """A view is free to recolour itself for its content; chrome is not content."""
    scheme("#31363b", "#fcfcfc")
    widget = button(host, qtbot)
    from_scheme = fill_color(widget)

    recoloured = QPalette(host.palette())
    recoloured.setColor(QPalette.ColorRole.Window, QColor("#ff00ff"))
    host.setPalette(recoloured)
    assert fill_color(widget) == from_scheme


def test_the_surface_is_translucent_but_the_rim_reads_against_it(host, qtbot):
    """Contrasting outline, per hig/displaying_content.md, over live artwork."""
    widget = button(host, qtbot)
    assert 0 < fill_color(widget).alphaF() < 1
    assert fill_color(widget, active=True).alphaF() > fill_color(widget).alphaF()
    assert outline_color(widget).alphaF() > 0


def test_the_button_is_a_disc_sized_off_the_style_not_a_constant(host, qtbot):
    """hig/accessibility.md wants the UI to survive a larger system font."""
    widget = button(host, qtbot)
    assert widget.width() == widget.height()
    inscribed = widget.size_px - 2 * OverlayButton.PADDING
    # The glyph must clear the inscribed square of the disc, not its bounding box.
    assert inscribed >= widget.iconSize().width() * math.sqrt(2)


def test_an_unthemed_name_falls_back_to_the_glyph_not_an_empty_disc(host, qtbot):
    """Both the -symbolic ask and the plain name can miss on a non-KDE session."""
    widget = OverlayButton(host, "no-such-icon-anywhere", "⛶", "Leave", lambda: None)
    qtbot.addWidget(widget)
    assert widget.icon().isNull()
    assert widget.text() == "⛶"


def test_the_glyph_is_drawn_at_icon_size_not_stretched_to_the_disc(host, qtbot):
    """QIcon.paint scales to the rect it is handed, so setIconSize alone is a lie.

    Passing self.rect() drew a full-bleed glyph hard against the rim, and made
    the disc-sizing maths invisible -- growing the button grew the icon with it.
    """
    widget = button(host, qtbot)
    rect = widget.icon_rect()
    assert rect.size() == widget.iconSize()
    assert rect.center() == widget.rect().center()
    # and it clears the disc's inscribed square, so nothing touches the rim
    inscribed = widget.size_px / math.sqrt(2)
    assert rect.width() < inscribed


def test_stacked_buttons_do_not_overlap(host, qtbot):
    top, below = button(host, qtbot, row=0), button(host, qtbot, row=1)
    assert not top.geometry().intersects(below.geometry())
    assert below.y() > top.y()


def test_toast_reserves_its_padding_without_a_stylesheet(host, qtbot):
    """`padding` moved to contentsMargins, which QLabel counts in sizeHint."""
    toast = Toast(host)
    qtbot.addWidget(toast)
    toast.setText("Press Esc to exit fullscreen")
    toast.adjustSize()
    margins = toast.contentsMargins()
    metrics = toast.fontMetrics()
    text = metrics.horizontalAdvance(toast.text())
    assert toast.width() >= text + margins.left() + margins.right()
    assert toast.height() >= metrics.height() + margins.top() + margins.bottom()
