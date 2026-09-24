import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from tarot_canvas.ui.palette import muted_text
from tarot_canvas.ui.widgets import placeholder_message
from tarot_canvas.ui.widgets.placeholder_message import (
    ICON_SIZE,
    PlaceholderMessage,
    tint_icon,
)


def square_icon():
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.black)
    return QIcon(pixmap)


@pytest.fixture
def theme_has_icon(monkeypatch):
    """Any icon name resolves to an opaque square"""
    monkeypatch.setattr(placeholder_message.QIcon, "hasThemeIcon", staticmethod(lambda _: True))
    monkeypatch.setattr(
        placeholder_message.QIcon, "fromTheme", staticmethod(lambda _: square_icon())
    )


def render(qtbot, message):
    qtbot.addWidget(message)
    message.resize(300, 300)
    message.layout().activate()
    return message.grab().toImage()


def test_tint_icon_is_drawn_at_device_pixels(qapp):
    image = tint_icon(square_icon(), 24, 2, Qt.GlobalColor.darkCyan)

    assert (image.width(), image.height()) == (48, 48)
    assert image.devicePixelRatio() == 2
    opaque = [
        image.pixelColor(x, y)
        for x in range(48)
        for y in range(48)
        if image.pixelColor(x, y).alpha() == 255
    ]
    assert opaque
    assert all(colour == QColor(Qt.GlobalColor.darkCyan) for colour in opaque)


def test_empty_strings_hide_every_label(qtbot):
    message = PlaceholderMessage("story-editor")
    qtbot.addWidget(message)

    assert message.heading.isHidden()
    assert message.explanation.isHidden()
    assert message.footnote.isHidden()


def test_strings_show_their_labels(qtbot):
    message = PlaceholderMessage("story-editor", "Heading", "Explanation", "Footnote")
    qtbot.addWidget(message)

    assert not message.heading.isHidden()
    assert not message.explanation.isHidden()
    assert not message.footnote.isHidden()


def test_the_footnote_is_smaller_than_the_explanation(qtbot):
    message = PlaceholderMessage("story-editor", "Heading", "Explanation", "Footnote")
    qtbot.addWidget(message)

    footnote = message.footnote.fontInfo().pointSizeF()
    assert footnote < message.explanation.fontInfo().pointSizeF()


def test_links_in_the_explanation_and_footnote_open_in_the_browser(qtbot):
    link = '<a href="https://example.org">x</a>'
    message = PlaceholderMessage("story-editor", "Heading", link, link)
    qtbot.addWidget(message)

    assert message.explanation.openExternalLinks()
    assert message.footnote.openExternalLinks()


@pytest.mark.parametrize("width", [300, 1200])
def test_wrapped_text_gets_the_height_it_needs_at_any_width(qtbot, width):
    """Sized at one width and laid out at another, a centred label's text is cut off"""
    long_text = "word " * 60
    page = QWidget()
    layout = QVBoxLayout(page)
    message = PlaceholderMessage("story-editor", long_text, long_text, long_text)
    layout.addWidget(message)
    layout.addStretch(1)
    qtbot.addWidget(page)
    page.resize(width, 2000)
    page.show()
    qtbot.waitExposed(page)

    for label in (message.heading, message.explanation, message.footnote):
        geometry = label.geometry()
        assert geometry.width() == min(message.width(), label.maximumWidth())
        assert geometry.height() >= label.heightForWidth(geometry.width())


def test_a_missing_theme_icon_draws_nothing(qtbot):
    message = PlaceholderMessage("no-such-icon-xyz")

    image = render(qtbot, message)

    assert message.icon is None
    background = image.pixel(0, 0)
    assert all(
        image.pixel(x, y) == background for x in range(image.width()) for y in range(image.height())
    )


def test_the_icon_takes_the_muted_text_colour(qtbot, theme_has_icon, theme_palette):
    message = PlaceholderMessage("any")
    message.setPalette(theme_palette)

    image = render(qtbot, message)

    # Compared as 8-bit RGB: muted_text keeps QColor's 16-bit channels, the image doesn't
    muted = muted_text(theme_palette).rgb()
    centre = message.icon_slot.geometry().center()
    assert message.icon_slot.size().width() == ICON_SIZE
    assert image.pixelColor(centre).rgb() == muted
    assert image.pixelColor(QPoint(0, 0)).rgb() != muted


def test_a_palette_change_recolours_the_labels(qtbot, theme_palette):
    message = PlaceholderMessage("story-editor", "Heading", "Explanation", "Footnote")
    qtbot.addWidget(message)

    message.setPalette(theme_palette)

    for label in (message.heading, message.explanation, message.footnote):
        assert label.palette().color(label.foregroundRole()) == muted_text(theme_palette)


def test_there_is_no_button_without_a_helpful_action(qtbot):
    message = PlaceholderMessage("story-editor", "Heading")
    qtbot.addWidget(message)

    assert message.helpful_button is None


def test_the_helpful_action_is_a_button_under_the_text(qtbot):
    from PyQt6.QtGui import QAction

    action = QAction("Do the thing")
    message = PlaceholderMessage("story-editor", "Heading", helpful_action=action)
    qtbot.addWidget(message)
    layout = message.layout()

    assert message.helpful_button.text() == "Do the thing"
    assert layout.indexOf(message.helpful_button) > layout.indexOf(message.heading)
    with qtbot.waitSignal(action.triggered):
        qtbot.mouseClick(message.helpful_button, Qt.MouseButton.LeftButton)


def test_the_button_follows_its_action(qtbot):
    from PyQt6.QtGui import QAction

    action = QAction("Before")
    message = PlaceholderMessage("story-editor", "Heading", helpful_action=action)
    qtbot.addWidget(message)

    action.setText("After")
    action.setEnabled(False)

    assert message.helpful_button.text() == "After"
    assert not message.helpful_button.isEnabled()


def test_a_tagged_heading_is_shown_with_its_tags(qtbot):
    tagged = "<clankertext>a heading</clankertext>"
    message = PlaceholderMessage("story-editor", tagged)
    qtbot.addWidget(message)

    assert message.heading.text() == tagged
    assert message.heading.textFormat() == Qt.TextFormat.PlainText
