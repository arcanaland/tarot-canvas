from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from tarot_canvas.ui.palette import message_fill
from tarot_canvas.ui.widgets.inline_message import InlineMessage

TAGGED = "<clankertext>a placeholder</clankertext>"


def test_a_tagged_string_reaches_the_screen_with_its_tags(qtbot):
    message = InlineMessage()
    qtbot.addWidget(message)

    message.show_message(TAGGED)

    assert "<clankertext>" in message.label.text()
    assert message.label.textFormat() == Qt.TextFormat.PlainText


def test_each_action_gets_a_button_and_a_new_message_replaces_them(qtbot):
    message = InlineMessage()
    qtbot.addWidget(message)
    first, second = QAction("One", message), QAction("Two", message)

    message.show_message("text", [first, second])
    assert [b.defaultAction() for b in message.action_buttons] == [first, second]

    message.show_message("text", [second])
    assert [b.defaultAction() for b in message.action_buttons] == [second]


def test_the_close_button_hides_it_and_says_so(qtbot):
    message = InlineMessage()
    qtbot.addWidget(message)
    message.show_message("text")

    with qtbot.waitSignal(message.dismissed):
        qtbot.mouseClick(message.close_button, Qt.MouseButton.LeftButton)

    assert message.isHidden()


def test_hiding_it_is_not_a_dismissal(qtbot):
    message = InlineMessage()
    qtbot.addWidget(message)
    message.show_message("text")

    with qtbot.assertNotEmitted(message.dismissed):
        message.hide()


def test_showing_it_leaves_focus_where_it_was_and_its_actions_are_reachable_by_tab(qtbot):
    page = QWidget()
    layout = QVBoxLayout(page)
    message = InlineMessage(parent=page)
    field = QLineEdit(page)
    layout.addWidget(message)
    layout.addWidget(field)
    qtbot.addWidget(page)
    with qtbot.waitActive(page):
        page.show()
        page.activateWindow()
    field.setFocus()
    qtbot.waitUntil(field.hasFocus)

    message.show_message("text", [QAction("Undo", page)])

    assert field.hasFocus()
    assert message.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert message.action_buttons[0].focusPolicy() & Qt.FocusPolicy.TabFocus


def test_its_fill_follows_the_palette(qtbot, theme_palette):
    message = InlineMessage()
    qtbot.addWidget(message)
    message.show_message("text")
    message.resize(300, 40)

    message.setPalette(theme_palette)
    image = message.grab().toImage()

    # Compared as 8-bit RGB: the palette keeps QColor's 16-bit channels, the image doesn't
    assert image.pixelColor(QPoint(3, 20)).rgb() == message_fill(theme_palette).rgb()
